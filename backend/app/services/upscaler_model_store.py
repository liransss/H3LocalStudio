from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.models.upscaler_manifest import UPSCALER_MANIFEST, UpscalerModelFile, UpscalerModelManifest


FLASH_NODE_REPOSITORY = "https://github.com/naxci1/ComfyUI-FlashVSR_Stable.git"
FLASH_NODE_COMMIT = "f7f55bae4c0e82b18b190d4b62a977995507c51c"
TRITON_WINDOWS_VERSION = "3.7.1.post27"


class UpscalerModelsNotReady(RuntimeError):
    pass


class UpscalerModelStore:
    def __init__(
        self,
        comfyui_root: Path,
        cache_root: Path,
        *,
        managed_runtime: bool,
        manifest: UpscalerModelManifest = UPSCALER_MANIFEST,
    ) -> None:
        self.comfyui_root = comfyui_root
        self.cache_file = cache_root / "upscaler_model_verification.json"
        self.manifest = manifest
        self.managed_runtime = managed_runtime

    @property
    def flash_node_path(self) -> Path:
        return self.comfyui_root / "custom_nodes" / "ComfyUI-FlashVSR_Stable"

    def path_for(self, component: UpscalerModelFile) -> Path:
        return component.destination(self.comfyui_root)

    def component_status(self, component: UpscalerModelFile) -> dict[str, Any]:
        path = self.path_for(component)
        partial = path.with_name(f"{path.name}.part")
        cache = self._verification_cache()
        if path.is_file():
            actual_size = path.stat().st_size
            if actual_size != component.size or self._cache_invalid(component, path, cache):
                status = "invalid"
            elif self._cache_verified(component, path, cache):
                status = "verified"
            else:
                status = "installed"
        elif partial.is_file():
            actual_size = partial.stat().st_size
            status = "partial"
        else:
            actual_size = 0
            status = "missing"
        return {
            "id": component.id,
            "filename": component.filename,
            "model_dir": component.model_dir,
            "role": component.role,
            "required": component.required,
            "compatible_families": list(component.compatible_families),
            "path": str(path),
            "status": status,
            "size": component.size,
            "bytes_present": actual_size,
            "sha256": component.sha256,
            "source_repo": component.repo,
            "source_revision": component.revision,
        }

    def family_status(self, family: str) -> dict[str, Any]:
        components = [self.component_status(item) for item in self.manifest.family_files(family)]
        models_installed = all(item["status"] in {"installed", "verified"} for item in components)
        models_verified = all(item["status"] == "verified" for item in components)
        runtime = self.runtime_status(family)
        ready = models_verified and runtime["ready"]
        installed = models_installed and runtime["ready"]
        return {
            "id": family,
            "name": self.manifest.family_names[family],
            "category": "upscaler",
            "status": "verified" if ready else "installed" if installed else "incomplete",
            "installed": installed,
            "models_installed": models_installed,
            "ready": ready,
            "verified": ready,
            "total_size": self.manifest.family_size(family),
            "manifest_version": self.manifest.version,
            "components": components,
            "runtime": runtime,
        }

    def all_status(self) -> list[dict[str, Any]]:
        return [self.family_status(family) for family in self.manifest.families]

    def runtime_status(self, family: str) -> dict[str, Any]:
        if family == "seedvr2":
            native = self.comfyui_root / "comfy_extras" / "nodes_seedvr.py"
            return {
                "ready": native.is_file(),
                "kind": "native_comfyui",
                "version": "ComfyUI native" if native.is_file() else None,
                "path": str(native),
                "reason": None if native.is_file() else "This ComfyUI build does not contain native SeedVR2 nodes.",
            }
        if family != "flashvsr":
            raise ValueError(f"Unknown upscaler family: {family}")
        path = self.flash_node_path
        commit = _git_output(path, "rev-parse", "HEAD") if path.is_dir() else None
        triton_version = _comfy_package_version(self.comfyui_root, "triton-windows")
        ready = commit == FLASH_NODE_COMMIT and triton_version == TRITON_WINDOWS_VERSION
        reasons: list[str] = []
        if commit != FLASH_NODE_COMMIT:
            reasons.append("Pinned FlashVSR ComfyUI integration is not installed")
        if triton_version != TRITON_WINDOWS_VERSION:
            reasons.append(f"triton-windows {TRITON_WINDOWS_VERSION} is required")
        return {
            "ready": ready,
            "kind": "comfy_registry_node",
            "version": commit,
            "path": str(path),
            "dependency": f"triton-windows {triton_version}" if triton_version else None,
            "reason": "; ".join(reasons) or None,
        }

    def require_family(self, family: str) -> tuple[Path, ...]:
        status = self.family_status(family)
        if not status["ready"]:
            missing = [
                f"{item['filename']} ({item['status']})"
                for item in status["components"]
                if item["status"] != "verified"
            ]
            if status["runtime"].get("reason"):
                missing.append(status["runtime"]["reason"])
            raise UpscalerModelsNotReady(
                f"{status['name']} is not installed and verified: "
                + ", ".join(missing)
                + ". Open Models to install or repair it."
            )
        return tuple(self.path_for(item) for item in self.manifest.family_files(family))

    async def prepare_family(self, family: str, repair: bool) -> None:
        if family == "seedvr2":
            if not self.runtime_status(family)["ready"]:
                raise RuntimeError("Native SeedVR2 requires a current managed ComfyUI build")
            return
        if family != "flashvsr":
            raise ValueError(f"Unknown upscaler family: {family}")
        if not self.managed_runtime and not self.runtime_status(family)["ready"]:
            raise RuntimeError("H3 Local Studio never modifies an external ComfyUI. Install the pinned FlashVSR node manually.")
        await asyncio.to_thread(self._prepare_flash_runtime, repair)

    def _prepare_flash_runtime(self, repair: bool) -> None:
        target = self.flash_node_path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _run(["git", "clone", "--filter=blob:none", FLASH_NODE_REPOSITORY, str(target)])
            _run(["git", "checkout", "--detach", FLASH_NODE_COMMIT], cwd=target)
        elif not (target / ".git").is_dir():
            raise RuntimeError(f"FlashVSR target exists but is not a managed Git checkout: {target}")
        commit = _git_output(target, "rev-parse", "HEAD")
        if commit != FLASH_NODE_COMMIT:
            dirty = _git_output(target, "status", "--porcelain")
            if not repair:
                raise RuntimeError("FlashVSR runtime is not at the pinned revision. Choose Repair to restore it.")
            if dirty:
                raise RuntimeError("FlashVSR runtime has local changes. Repair stopped to preserve them.")
            _run(["git", "fetch", "origin", FLASH_NODE_COMMIT], cwd=target)
            _run(["git", "checkout", "--detach", FLASH_NODE_COMMIT], cwd=target)
        installed = _comfy_package_version(self.comfyui_root, "triton-windows")
        if installed != TRITON_WINDOWS_VERSION:
            python = _comfy_python(self.comfyui_root)
            _run([str(python), "-m", "pip", "install", "--no-deps", f"triton-windows=={TRITON_WINDOWS_VERSION}"])

    async def verify_component(self, component: UpscalerModelFile) -> bool:
        path = self.path_for(component)
        if not path.is_file() or path.stat().st_size != component.size:
            return False
        digest = await asyncio.to_thread(_sha256_file, path)
        cache = self._verification_cache()
        cache.setdefault("components", {})[component.id] = {
            "state": "verified" if digest == component.sha256 else "invalid",
            "sha256": digest,
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        self._write_cache(cache)
        return digest == component.sha256

    def _verification_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return payload if payload.get("manifest_version") == self.manifest.version else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _cache_verified(component: UpscalerModelFile, path: Path, cache: dict[str, Any]) -> bool:
        record = cache.get("components", {}).get(component.id, {})
        stat = path.stat()
        return (
            record.get("state") == "verified"
            and record.get("sha256") == component.sha256
            and record.get("size") == stat.st_size
            and record.get("mtime_ns") == stat.st_mtime_ns
        )

    @staticmethod
    def _cache_invalid(component: UpscalerModelFile, path: Path, cache: dict[str, Any]) -> bool:
        record = cache.get("components", {}).get(component.id, {})
        stat = path.stat()
        return record.get("state") == "invalid" and record.get("size") == stat.st_size and record.get("mtime_ns") == stat.st_mtime_ns

    def _write_cache(self, payload: dict[str, Any]) -> None:
        payload["manifest_version"] = self.manifest.version
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.cache_file)


def _run(arguments: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        details = (result.stderr or result.stdout)[-4000:]
        raise RuntimeError(f"Runtime setup failed: {' '.join(arguments[:3])}\n{details}")


def _git_output(path: Path, *arguments: str) -> str | None:
    if not path.is_dir():
        return None
    result = subprocess.run(
        ["git", *arguments],
        cwd=path,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _comfy_python(root: Path) -> Path:
    for candidate in (root / ".venv" / "Scripts" / "python.exe", root / "venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    raise RuntimeError("Managed ComfyUI Python environment was not found")


def _comfy_package_version(root: Path, package: str) -> str | None:
    try:
        python = _comfy_python(root)
    except RuntimeError:
        return None
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata as metadata, sys; "
            "\ntry: print(metadata.version(sys.argv[1]))"
            "\nexcept metadata.PackageNotFoundError: pass",
            package,
        ],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    version = result.stdout.strip()
    return version or None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
