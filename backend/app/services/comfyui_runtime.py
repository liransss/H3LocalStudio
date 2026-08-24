from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.config import AppSettings
from app.providers.comfyui import ComfyUIClient, ComfyUIUnavailable


logger = logging.getLogger(__name__)


class ComfyUIRuntime:
    def __init__(self, settings: AppSettings, client: ComfyUIClient):
        self.settings = settings
        self.client = client
        self.process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None

    async def ensure_running(self) -> dict[str, Any]:
        health = await self.client.health()
        if health["running"]:
            return health
        if self.settings.comfyui_mode == "external":
            raise ComfyUIUnavailable("Local inference engine is not running on the configured external address")
        return await self.start()

    async def start(self) -> dict[str, Any]:
        health = await self.client.health()
        if health["running"]:
            return health
        root = self.settings.resolved_comfyui_path
        main = root / "main.py"
        if not main.is_file():
            raise ComfyUIUnavailable(
                f"Managed ComfyUI was not found at {root}. Configure an existing installation in Settings."
            )
        python = self._python_executable(root)
        command = [
            str(python), str(main), "--listen", self.settings.comfyui_host,
            "--port", str(self.settings.comfyui_port), "--disable-auto-launch",
        ]
        if self.settings.comfyui_profile == "low_vram":
            command.append("--lowvram")
        log_path = self.settings.directories["logs"] / "comfyui.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = log_path.open("ab", buffering=0)
        child_environment = os.environ.copy()
        child_environment["PYTHONUTF8"] = "1"
        child_environment["PYTHONIOENCODING"] = "utf-8"
        logger.info("Starting managed ComfyUI command=%s", command)
        self.process = subprocess.Popen(
            command, cwd=root, stdin=subprocess.DEVNULL, stdout=self._log_handle,
            stderr=subprocess.STDOUT, env=child_environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(90):
            await asyncio.sleep(1)
            if self.process.poll() is not None:
                raise ComfyUIUnavailable(f"Managed ComfyUI exited during startup. See {log_path}")
            health = await self.client.health()
            if health["running"]:
                logger.info("Managed ComfyUI ready version=%s", health.get("version"))
                return health
        await self.stop()
        raise ComfyUIUnavailable(f"Managed ComfyUI did not become ready within 90 seconds. See {log_path}")

    async def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self.process.wait), timeout=15)
            except TimeoutError:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
        self.process = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    async def update(self) -> dict[str, Any]:
        if self.settings.comfyui_mode != "managed":
            raise RuntimeError("External ComfyUI installations are never modified by H3 Local Studio")
        root = self.settings.resolved_comfyui_path
        if not (root / ".git").is_dir():
            raise RuntimeError("The managed ComfyUI folder is not a Git checkout and cannot be updated automatically")
        status = await asyncio.to_thread(
            subprocess.run, ["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, check=True,
        )
        if status.stdout.strip():
            raise RuntimeError("Managed ComfyUI has local changes. Update was stopped to preserve them.")
        result = await asyncio.to_thread(
            subprocess.run, ["git", "pull", "--ff-only"], cwd=root,
            capture_output=True, text=True, check=True,
        )
        return {"updated": True, "message": result.stdout.strip()}

    @staticmethod
    def _python_executable(root: Path) -> Path:
        candidates = (
            root / ".venv" / "Scripts" / "python.exe",
            root / "venv" / "Scripts" / "python.exe",
            root.parent / "python_embeded" / "python.exe",
            Path(sys.executable),
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise ComfyUIUnavailable("No Python executable was found for managed ComfyUI")
