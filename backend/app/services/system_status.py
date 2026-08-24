from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psutil

from app.config import AppSettings
from app.providers.comfyui import ComfyUIClient
from app.providers.ffmpeg import find_ffmpeg
from app.services.model_store import H3ModelStore
from app.providers.upscalers import VideoUpscalerRegistry
from app.services.upscaler_model_store import UpscalerModelStore


logger = logging.getLogger(__name__)


async def _nvidia_status() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable and os.name == "nt":
        system_candidate = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "nvidia-smi.exe"
        executable = str(system_candidate) if system_candidate.is_file() else None
    if not executable:
        return {"available": False, "name": None, "vram_total_mb": None, "vram_free_mb": None, "cuda": False}
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [executable, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        first_line = result.stdout.decode(errors="replace").strip().splitlines()[0]
        name, total, free = [part.strip() for part in first_line.split(",", 2)]
        return {
            "available": True,
            "name": name,
            "vram_total_mb": int(total),
            "vram_free_mb": int(free),
            "cuda": True,
        }
    except Exception as error:
        logger.warning("NVIDIA status detection failed: %s: %s", type(error).__name__, error)
        return {"available": False, "name": None, "vram_total_mb": None, "vram_free_mb": None, "cuda": False}


async def get_system_status(
    settings: AppSettings,
    models: H3ModelStore | None = None,
    upscaler_models: UpscalerModelStore | None = None,
    upscalers: VideoUpscalerRegistry | None = None,
) -> dict[str, Any]:
    gpu, comfyui, provider_status = await asyncio.gather(
        _nvidia_status(),
        ComfyUIClient(settings.comfyui_url).health(),
        upscalers.status() if upscalers else asyncio.sleep(0, result=[]),
    )
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(settings.data_root.anchor or str(settings.data_root))
    ffmpeg = find_ffmpeg(settings.ffmpeg_path)
    model_status = models.family_status("fl2va") if models else {"ready": False, "status": "unknown"}
    ref2va_status = models.family_status("ref2va") if models else {"ready": False, "status": "unknown"}
    flash_status = upscaler_models.family_status("flashvsr") if upscaler_models else {"ready": False}
    seed_status = upscaler_models.family_status("seedvr2") if upscaler_models else {"ready": False}
    return {
        "app": {"name": settings.app_name, "version": settings.version, "mock_mode": settings.mock_mode},
        "gpu": {**gpu, "vram_used_mb": (
            gpu["vram_total_mb"] - gpu["vram_free_mb"]
            if gpu.get("vram_total_mb") is not None and gpu.get("vram_free_mb") is not None
            else None
        )},
        "memory": {"total_mb": round(memory.total / 1024**2), "available_mb": round(memory.available / 1024**2)},
        "disk": {
            "root": str(settings.data_root),
            "free_gb": round(disk.free / 1024**3, 1),
            "total_gb": round(disk.total / 1024**3, 1),
        },
        "comfyui": comfyui,
        "ffmpeg": {"available": bool(ffmpeg), "path": ffmpeg},
        "models": {
            "minimax_h3": "ready" if model_status["ready"] else "missing_models",
            "minimax_h3_ref2va": "ready" if ref2va_status["ready"] else "missing_models",
            "manifest_version": model_status.get("manifest_version"),
            "flashvsr": "ready" if flash_status["ready"] else "missing_models",
            "seedvr2": "ready" if seed_status["ready"] else "missing_models",
        },
        "inference": {
            "mode": "mock" if settings.mock_mode else "local_gpu",
            "comfyui_mode": settings.comfyui_mode,
            "profile": settings.comfyui_profile,
        },
        "upscaler": {
            "available": any(item.available for item in provider_status),
            "provider": next((item.display_name for item in provider_status if item.available), None),
            "providers": [asdict(item) for item in provider_status],
        },
    }
