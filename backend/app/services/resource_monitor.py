from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from typing import Any

import psutil


def generation_resource_guard(*, ref2va: bool, reference_count: int = 0) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    available_gb = memory.available / 1024**3
    minimum_ram = 4.0 if ref2va else 3.0
    if available_gb < minimum_ram:
        mode = "Reference-to-Video" if ref2va else "MiniMax H3"
        raise RuntimeError(
            f"Only {available_gb:.1f} GB of system RAM is available. {mode} cannot start safely. "
            "Close memory-intensive applications and retry; H3 Local Studio did not terminate them."
        )
    warnings: list[str] = []
    warning_threshold = 12.0 if ref2va else 8.0
    if available_gb < warning_threshold:
        warnings.append(f"Low system RAM for this workflow: {available_gb:.1f} GB available")
    if ref2va and reference_count >= 4:
        warnings.append(
            "Large multi-reference sets increase system RAM pressure; preview resolution is recommended first."
        )
    gpu = gpu_snapshot()
    minimum_vram = 5.0 if ref2va else 3.0
    if gpu and gpu["memory_free_gb"] < minimum_vram:
        raise RuntimeError(
            f"Only {gpu['memory_free_gb']:.1f} GB of GPU memory is available. Close other GPU workloads "
            "and retry; H3 Local Studio did not terminate them."
        )
    if gpu and gpu["memory_free_gb"] < 8:
        warnings.append(f"Low GPU memory: {gpu['memory_free_gb']:.1f} GB available")
    return {
        "ram_available_gb": round(available_gb, 2),
        "gpu": gpu,
        "reference_count": reference_count,
        "warnings": warnings,
    }


class ResourceTelemetry:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._started = time.perf_counter()
        self._samples = 0
        self._peak_ram_used_gb = 0.0
        self._minimum_ram_available_gb = float("inf")
        self._peak_vram_used_gb = 0.0
        self._minimum_vram_free_gb = float("inf")
        self._peak_gpu_utilization_percent = 0.0
        self._gpu_samples = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._sample_until_cancelled())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.to_thread(self._sample_once)

    def summary(self) -> dict[str, Any]:
        return {
            "sample_interval_seconds": 1.0,
            "sample_count": self._samples,
            "measurement_seconds": round(time.perf_counter() - self._started, 3),
            "peak_system_ram_used_gb": round(self._peak_ram_used_gb, 2),
            "minimum_system_ram_available_gb": (
                round(self._minimum_ram_available_gb, 2)
                if self._minimum_ram_available_gb != float("inf") else None
            ),
            "gpu_sample_count": self._gpu_samples,
            "peak_vram_used_gb": round(self._peak_vram_used_gb, 2) if self._gpu_samples else None,
            "minimum_vram_free_gb": (
                round(self._minimum_vram_free_gb, 2)
                if self._minimum_vram_free_gb != float("inf") else None
            ),
            "peak_gpu_utilization_percent": (
                round(self._peak_gpu_utilization_percent, 1) if self._gpu_samples else None
            ),
        }

    async def _sample_until_cancelled(self) -> None:
        while True:
            await asyncio.to_thread(self._sample_once)
            await asyncio.sleep(1)

    def _sample_once(self) -> None:
        memory = psutil.virtual_memory()
        self._peak_ram_used_gb = max(self._peak_ram_used_gb, memory.used / 1024**3)
        self._minimum_ram_available_gb = min(self._minimum_ram_available_gb, memory.available / 1024**3)
        gpu = gpu_snapshot()
        if gpu:
            self._gpu_samples += 1
            self._peak_vram_used_gb = max(self._peak_vram_used_gb, gpu["memory_used_gb"])
            self._minimum_vram_free_gb = min(self._minimum_vram_free_gb, gpu["memory_free_gb"])
            self._peak_gpu_utilization_percent = max(
                self._peak_gpu_utilization_percent, gpu["utilization_percent"]
            )
        self._samples += 1


def gpu_snapshot() -> dict[str, float] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    result = subprocess.run(
        [
            executable,
            "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode or not result.stdout.strip():
        return None
    try:
        total, used, free, utilization = [
            float(value.strip()) for value in result.stdout.splitlines()[0].split(",")
        ]
    except (TypeError, ValueError):
        return None
    return {
        "memory_total_gb": round(total / 1024, 3),
        "memory_used_gb": round(used / 1024, 3),
        "memory_free_gb": round(free / 1024, 3),
        "utilization_percent": utilization,
    }
