from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import psutil

from app.providers.base import (
    ProgressCallback,
    UpscaleArtifact,
    UpscalerAvailability,
    VideoUpscalerProvider,
)
from app.providers.comfyui import ComfyUIClient, ComfyUIExecutionError, parse_output_descriptor
from app.providers.ffmpeg import FFmpegUpscaler, finalize_ai_upscale
from app.services.ffprobe import MediaValidationError, probe_media
from app.services.upscaler_model_store import UpscalerModelStore
from app.workflows.upscale import UpscaleWorkflow, build_flashvsr_workflow, build_seedvr2_workflow


logger = logging.getLogger(__name__)


class RuntimeController(Protocol):
    async def ensure_running(self) -> dict[str, Any]: ...


class InstallManager(Protocol):
    def start_install(self, family: str, *, repair: bool = False) -> dict[str, Any]: ...


class ComfyAIUpscaler(VideoUpscalerProvider):
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        client: ComfyUIClient,
        runtime: RuntimeController,
        models: UpscalerModelStore,
        installer: InstallManager,
        ffmpeg: str | None,
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.model_family = provider_id
        self.client = client
        self.runtime = runtime
        self.models = models
        self.installer = installer
        self.ffmpeg = ffmpeg
        self.active_prompt_id: str | None = None

    def required_models(self) -> tuple[str, ...]:
        return tuple(item.filename for item in self.models.manifest.family_files(self.model_family))

    async def availability(self) -> UpscalerAvailability:
        status = self.models.family_status(self.model_family)
        ffmpeg_ready = bool(self.ffmpeg)
        available = bool(status["ready"] and ffmpeg_ready)
        reason = status["runtime"].get("reason")
        if not status["ready"] and not reason:
            reason = "Required model files are not installed and verified."
        if not ffmpeg_ready:
            reason = "FFmpeg is required for H.264 output and audio preservation."
        return UpscalerAvailability(
            provider_id=self.provider_id,
            display_name=self.display_name,
            available=available,
            models_ready=bool(status["ready"]),
            runtime_ready=bool(status["runtime"]["ready"] and ffmpeg_ready),
            reason=reason,
            model_family=self.model_family,
        )

    async def install(self, *, confirmed: bool, repair: bool = False) -> dict[str, Any]:
        if not confirmed:
            status = self.models.family_status(self.model_family)
            raise RuntimeError(
                f"Explicit confirmation is required before downloading {status['total_size']:,} bytes."
            )
        return self.installer.start_install(self.model_family, repair=repair)

    async def validate(self) -> UpscalerAvailability:
        availability = await self.availability()
        if not availability.available:
            return availability
        health = await self.runtime.ensure_running()
        if not health.get("running"):
            return UpscalerAvailability(
                self.provider_id,
                self.display_name,
                False,
                True,
                False,
                "The local inference engine could not be started.",
                self.model_family,
            )
        workflow = self._workflow("H3LocalStudio/validation.mp4", "H3LocalStudio/validation", 1, 1920, 1080)
        try:
            await self.client.validate_nodes(workflow.required_node_classes)
        except Exception as error:
            return UpscalerAvailability(
                self.provider_id,
                self.display_name,
                False,
                True,
                False,
                str(error),
                self.model_family,
            )
        return availability

    async def upscale(
        self,
        source: Path,
        destination: Path,
        resolution: str,
        progress: ProgressCallback,
        aspect_ratio: str = "16:9",
        seed: int = 0,
    ) -> UpscaleArtifact:
        if resolution != "1080p":
            raise ValueError("Phase 3 AI upscalers support 1080p only.")
        model_paths = self.models.require_family(self.model_family)
        source_metadata = await probe_media(self._ffprobe(), source, require_audio=False)
        target_width, target_height = FFmpegUpscaler._target_dimensions("1080p", aspect_ratio)
        content_width, content_height = _fit_dimensions(
            int(source_metadata["width"]), int(source_metadata["height"]), target_width, target_height
        )
        await progress(0.05, "Starting local inference engine")
        await self.runtime.ensure_running()
        try:
            await self.client.free_memory()
        except Exception as error:
            logger.warning("ComfyUI pre-upscale memory release failed: %s", error)
        await asyncio.sleep(0)
        guard = _resource_guard()
        telemetry = _ResourceTelemetry()
        await progress(0.09, "Staging the original video locally")
        staged = self.models.comfyui_root / "input" / "H3LocalStudio" / f"upscale-{uuid.uuid4()}.mp4"
        staged.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, staged)
        relative_input = staged.relative_to(self.models.comfyui_root / "input").as_posix()
        prefix = f"H3LocalStudio/upscale/{self.provider_id}/{destination.stem}"
        workflow = self._workflow(relative_input, prefix, seed, content_width, content_height)
        await self.client.validate_nodes(workflow.required_node_classes)
        raw_output = destination.with_name(f"{destination.stem}.{self.provider_id}.provider.mp4")
        timestamps: dict[str, float] = {}
        started = time.perf_counter()
        telemetry.start()

        def on_node(class_type: str) -> None:
            timestamps.setdefault(class_type, time.perf_counter())

        try:
            prompt_id, history = await self.client.execute(
                workflow,
                progress,
                lambda queued_id: setattr(self, "active_prompt_id", queued_id),
                on_node=on_node,
                node_stage=self._node_stage,
                node_progress=self._node_progress,
                progress_bounds=(0.2, 0.82),
            )
            descriptor = parse_output_descriptor(history, prompt_id, workflow.output_node_id)
            await progress(0.87, "Importing AI-upscaled frames")
            await self.client.download_output(descriptor, raw_output)
            inference_finished = time.perf_counter()
            await finalize_ai_upscale(
                self.ffmpeg,
                raw_output,
                source,
                destination,
                target_width,
                target_height,
                float(source_metadata["duration"]),
                progress,
            )
            await progress(0.97, "Validating 1080p video, timing, and audio")
            output_metadata = await probe_media(
                self._ffprobe(), destination, require_audio=bool(source_metadata.get("audio_present"))
            )
            _validate_upscaled_media(output_metadata, source_metadata, target_width, target_height)
            await telemetry.stop()
            metadata = {
                "provider": self.provider_id,
                "display_name": self.display_name,
                "model_files": [path.name for path in model_paths],
                "manifest_version": self.models.manifest.version,
                "provider_prompt_id": prompt_id,
                "source": source_metadata,
                "output": output_metadata,
                "target": {"width": target_width, "height": target_height},
                "content_target": {"width": content_width, "height": content_height},
                "resource_guard": guard,
                "resource_telemetry": telemetry.summary(),
                "pipeline": self._pipeline_metadata(),
                "model_prepare_seconds": _elapsed_between(timestamps, self._load_node(), self._inference_node()),
                "ai_processing_seconds": round(inference_finished - started, 3),
                "total_provider_seconds": round(time.perf_counter() - started, 3),
            }
            raw_output.unlink(missing_ok=True)
            return UpscaleArtifact(
                destination,
                self.provider_id,
                self.display_name,
                tuple(path.name for path in model_paths),
                self.models.manifest.version,
                prompt_id,
                metadata,
            )
        finally:
            await telemetry.stop()
            self.active_prompt_id = None
            staged.unlink(missing_ok=True)
            try:
                await self.client.free_memory()
            except Exception as error:
                logger.warning("ComfyUI post-upscale memory release failed: %s", error)

    async def cancel(self) -> None:
        try:
            await self.client.cancel_prompt(self.active_prompt_id)
        finally:
            self.active_prompt_id = None

    def _workflow(
        self, input_file: str, filename_prefix: str, seed: int, content_width: int, content_height: int
    ) -> UpscaleWorkflow:
        if self.provider_id == "flashvsr":
            return build_flashvsr_workflow(input_file, filename_prefix, seed)
        return build_seedvr2_workflow(input_file, filename_prefix, seed, content_width, content_height, split_latent=True)

    def _pipeline_metadata(self) -> dict[str, Any]:
        if self.provider_id == "flashvsr":
            return {
                "model": "FlashVSR-v1.1",
                "mode": "tiny",
                "scale": 2,
                "attention": "sdpa",
                "precision": "auto",
                "tiled_vae": True,
                "tiled_dit": True,
                "tile_size": 384,
                "tile_overlap": 32,
                "frame_chunk_size": 21,
                "input_resize_factor": 0.75,
            }
        return {
            "model": "SeedVR2 3B INT8 ConvRot",
            "steps": 1,
            "sampler": "euler/simple",
            "split_latent": True,
            "chunking": "auto",
            "temporal_overlap": 1,
            "vae_tiling": 512,
            "color_correction": "none",
        }

    def _load_node(self) -> str:
        return "FlashVSRInitPipe" if self.provider_id == "flashvsr" else "VAELoader"

    def _inference_node(self) -> str:
        return "FlashVSRNodeAdv" if self.provider_id == "flashvsr" else "KSampler"

    def _node_stage(self, class_type: str) -> str:
        stages = {
            "LoadVideo": "Reading original video and audio",
            "GetVideoComponents": "Separating frames and audio",
            "FlashVSRInitPipe": "Loading FlashVSR v1.1",
            "FlashVSRNodeAdv": "FlashVSR AI upscale",
            "VAELoader": "Loading SeedVR2 VAE",
            "UNETLoader": "Loading SeedVR2 3B INT8",
            "ImageScale": "Preparing 1080p reference frames",
            "VAEEncodeTiled": "Encoding SeedVR2 video latents",
            "SeedVR2TemporalChunk": "Planning VRAM-safe temporal chunks",
            "SeedVR2Conditioning": "Preparing SeedVR2 restoration",
            "KSampler": "SeedVR2 one-step restoration",
            "SeedVR2TemporalMerge": "Merging temporal chunks",
            "VAEDecodeTiled": "Decoding restored video",
            "SeedVR2PostProcessing": "Aligning restored frames",
            "CreateVideo": "Reattaching native audio",
            "SaveVideo": "Saving provider output",
        }
        return stages.get(class_type, f"Running {self.display_name}")

    def _node_progress(self, class_type: str) -> float:
        points = {
            "LoadVideo": 0.12,
            "GetVideoComponents": 0.14,
            "FlashVSRInitPipe": 0.18,
            "FlashVSRNodeAdv": 0.25,
            "ImageScale": 0.16,
            "VAELoader": 0.18,
            "UNETLoader": 0.2,
            "VAEEncodeTiled": 0.24,
            "SeedVR2TemporalChunk": 0.3,
            "KSampler": 0.36,
            "SeedVR2TemporalMerge": 0.75,
            "VAEDecodeTiled": 0.78,
            "SeedVR2PostProcessing": 0.84,
            "CreateVideo": 0.85,
            "SaveVideo": 0.86,
        }
        return points.get(class_type, 0.2)

    def _ffprobe(self) -> str | None:
        if not self.ffmpeg:
            return None
        executable = Path(self.ffmpeg)
        sibling = executable.with_name("ffprobe.exe" if executable.suffix else "ffprobe")
        return str(sibling) if sibling.is_file() else None


class VideoUpscalerRegistry:
    def __init__(self, providers: list[VideoUpscalerProvider]) -> None:
        self.providers = {provider.provider_id: provider for provider in providers}

    def get(self, provider_id: str) -> VideoUpscalerProvider:
        try:
            return self.providers[provider_id]
        except KeyError as error:
            raise ValueError(f"Unknown AI upscaler: {provider_id}") from error

    async def status(self) -> list[UpscalerAvailability]:
        return await asyncio.gather(*(provider.availability() for provider in self.providers.values()))


def _fit_dimensions(source_width: int, source_height: int, target_width: int, target_height: int) -> tuple[int, int]:
    scale = min(target_width / source_width, target_height / source_height)
    width = max(2, int(round(source_width * scale / 2)) * 2)
    height = max(2, int(round(source_height * scale / 2)) * 2)
    return min(width, target_width), min(height, target_height)


def _validate_upscaled_media(
    output: dict[str, Any], source: dict[str, Any], target_width: int, target_height: int
) -> None:
    if (output.get("width"), output.get("height")) != (target_width, target_height):
        raise MediaValidationError(
            f"Upscaler output is {output.get('width')}x{output.get('height')}; expected {target_width}x{target_height}."
        )
    if abs(float(output.get("fps", 0)) - 24.0) > 0.01:
        raise MediaValidationError(f"Upscaler output must be 24 FPS; got {output.get('fps')}.")
    duration_tolerance = 1 / 24 + 0.005
    if abs(float(output.get("duration", 0)) - float(source.get("duration", 0))) > duration_tolerance:
        raise MediaValidationError("Upscaler output duration does not match the original video.")
    if source.get("audio_present") and not output.get("audio_present"):
        raise MediaValidationError("Upscaler output lost the original audio stream.")


def _resource_guard() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    available_gb = memory.available / 1024**3
    if available_gb < 3:
        raise RuntimeError(
            f"Only {available_gb:.1f} GB of system RAM is available. Close memory-heavy applications and retry."
        )
    warnings: list[str] = []
    if available_gb < 8:
        warnings.append(f"Low system RAM: {available_gb:.1f} GB available")
    gpu = _gpu_snapshot()
    if gpu and gpu["memory_free_gb"] < 3:
        raise RuntimeError(
            f"Only {gpu['memory_free_gb']:.1f} GB of GPU memory is available. "
            "Close other GPU workloads and retry; H3 Local Studio did not terminate them."
        )
    if gpu and gpu["memory_free_gb"] < 6:
        warnings.append(f"Low GPU memory: {gpu['memory_free_gb']:.1f} GB available")
    return {
        "ram_available_gb": round(available_gb, 2),
        "gpu": gpu,
        "warnings": warnings,
    }


class _ResourceTelemetry:
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
                if self._minimum_ram_available_gb != float("inf")
                else None
            ),
            "gpu_sample_count": self._gpu_samples,
            "peak_vram_used_gb": round(self._peak_vram_used_gb, 2) if self._gpu_samples else None,
            "minimum_vram_free_gb": (
                round(self._minimum_vram_free_gb, 2)
                if self._minimum_vram_free_gb != float("inf")
                else None
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
        used_gb = memory.used / 1024**3
        available_gb = memory.available / 1024**3
        self._peak_ram_used_gb = max(self._peak_ram_used_gb, used_gb)
        self._minimum_ram_available_gb = min(self._minimum_ram_available_gb, available_gb)
        gpu = _gpu_snapshot()
        if gpu:
            self._gpu_samples += 1
            self._peak_vram_used_gb = max(self._peak_vram_used_gb, gpu["memory_used_gb"])
            self._minimum_vram_free_gb = min(self._minimum_vram_free_gb, gpu["memory_free_gb"])
            self._peak_gpu_utilization_percent = max(
                self._peak_gpu_utilization_percent, gpu["utilization_percent"]
            )
        self._samples += 1


def _gpu_snapshot() -> dict[str, float] | None:
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
        total, used, free, utilization = [float(value.strip()) for value in result.stdout.splitlines()[0].split(",")]
    except (TypeError, ValueError):
        return None
    return {
        "memory_total_gb": round(total / 1024, 3),
        "memory_used_gb": round(used / 1024, 3),
        "memory_free_gb": round(free / 1024, 3),
        "utilization_percent": utilization,
    }


def _elapsed_between(timestamps: dict[str, float], start: str, end: str) -> float | None:
    if start not in timestamps or end not in timestamps:
        return None
    return round(max(0.0, timestamps[end] - timestamps[start]), 3)
