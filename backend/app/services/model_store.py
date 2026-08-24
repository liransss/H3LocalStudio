from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from app.models.h3_manifest import H3_MANIFEST, H3ModelFile, H3ModelManifest


class ModelsNotReady(RuntimeError):
    pass


class H3ModelStore:
    def __init__(self, comfyui_root: Path, cache_root: Path, manifest: H3ModelManifest = H3_MANIFEST):
        self.comfyui_root = comfyui_root
        self.cache_file = cache_root / "h3_model_verification.json"
        self.manifest = manifest

    def path_for(self, component: H3ModelFile) -> Path:
        return component.destination(self.comfyui_root)

    def _verification_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return payload if payload.get("manifest_version") == self.manifest.version else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _cache_verified(self, component: H3ModelFile, path: Path, cache: dict[str, Any]) -> bool:
        record = cache.get("components", {}).get(component.id, {})
        try:
            stat = path.stat()
        except OSError:
            return False
        return (
            record.get("state") == "verified"
            and record.get("sha256") == component.sha256
            and record.get("size") == stat.st_size
            and record.get("mtime_ns") == stat.st_mtime_ns
        )

    def component_status(self, component: H3ModelFile) -> dict[str, Any]:
        path = self.path_for(component)
        partial = path.with_name(f"{path.name}.part")
        cache = self._verification_cache()
        if path.is_file():
            actual_size = path.stat().st_size
            if actual_size != component.size:
                status = "invalid"
            elif self._cache_invalid(component, path, cache):
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
            "shared": len(component.compatible_families) > 1,
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
        installed = all(item["status"] in {"installed", "verified"} for item in components)
        verified = all(item["status"] == "verified" for item in components)
        return {
            "id": family,
            "name": "MiniMax H3 FL2VA" if family == "fl2va" else "MiniMax H3 Ref2VA",
            "status": "verified" if verified else "installed" if installed else "incomplete",
            "installed": installed,
            "ready": verified,
            "verified": verified,
            "total_size": self.manifest.family_size(family),
            "manifest_version": self.manifest.version,
            "components": components,
        }

    def all_status(self) -> list[dict[str, Any]]:
        return [self.family_status(family) for family in self.manifest.families]

    def require_family(self, family: str) -> tuple[Path, ...]:
        unverified = [
            f"{status['filename']} ({status['status']})"
            for component in self.manifest.family_files(family)
            if (status := self.component_status(component))["status"] != "verified"
        ]
        if unverified:
            raise ModelsNotReady(
                "MiniMax H3 model files are not installed and verified: "
                + ", ".join(unverified)
                + ". Install, verify, or repair them on Models."
            )
        return tuple(self.path_for(item) for item in self.manifest.family_files(family))

    async def verify_component(self, component: H3ModelFile) -> bool:
        path = self.path_for(component)
        if not path.is_file() or path.stat().st_size != component.size:
            return False
        digest = await asyncio.to_thread(_sha256_file, path)
        cache = self._verification_cache()
        cache["manifest_version"] = self.manifest.version
        cache.setdefault("components", {})[component.id] = {
            "state": "verified" if digest == component.sha256 else "invalid",
            "sha256": digest,
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        self._write_cache(cache)
        return digest == component.sha256

    @staticmethod
    def _cache_invalid(component: H3ModelFile, path: Path, cache: dict[str, Any]) -> bool:
        record = cache.get("components", {}).get(component.id, {})
        try:
            stat = path.stat()
        except OSError:
            return False
        return (
            record.get("state") == "invalid"
            and record.get("size") == stat.st_size
            and record.get("mtime_ns") == stat.st_mtime_ns
        )

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.cache_file)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
