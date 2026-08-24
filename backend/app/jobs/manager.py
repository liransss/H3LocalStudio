from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import AppSettings
from app.jobs.state import assert_transition
from app.models.schemas import JobState
from app.providers.base import VideoGenerationProvider, VideoUpscalerProvider
from app.providers.ffmpeg import find_ffprobe
from app.providers.upscalers import VideoUpscalerRegistry
from app.repositories.studio import StudioRepository
from app.services.media import create_thumbnail, write_metadata
from app.services.ffprobe import MediaValidationError, probe_media
from app.services.h3_parameters import h3_resolution


logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProgressBroker:
    def __init__(self) -> None:
        self.subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        for queue in tuple(self.subscribers[job_id]):
            await queue.put(payload)

    def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers[job_id].add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers[job_id].discard(queue)


class JobManager:
    def __init__(
        self,
        settings: AppSettings,
        repository: StudioRepository,
        generation_provider: VideoGenerationProvider,
        upscalers: VideoUpscalerRegistry,
        mock_upscaler: VideoUpscalerProvider,
        ffmpeg: str | None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.generation_provider = generation_provider
        self.upscalers = upscalers
        self.mock_upscaler = mock_upscaler
        self.active_upscaler: VideoUpscalerProvider | None = None
        self.ffmpeg = ffmpeg
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.broker = ProgressBroker()
        self.cancelled: set[str] = set()
        self.worker: asyncio.Task[None] | None = None
        self.active_job_id: str | None = None
        self._stopping = False
        self.ffprobe = find_ffprobe(Path(ffmpeg) if ffmpeg else settings.ffmpeg_path)

    async def start(self) -> None:
        self.repository.recover_interrupted_jobs()
        self._stopping = False
        self.worker = asyncio.create_task(self._run(), name="h3-gpu-job-worker")

    async def stop(self) -> None:
        if self.worker:
            self._stopping = True
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def enqueue(self, job_id: str) -> None:
        await self.queue.put(job_id)

    async def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.repository.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] in {JobState.COMPLETED, JobState.FAILED, JobState.UPSCALE_FAILED, JobState.CANCELLED}:
            return job
        self.cancelled.add(job_id)
        await self._set_state(
            job_id,
            JobState.CANCELLED,
            job["progress"],
            "Cancelled",
            completed_at=now_iso(),
        )
        if self.active_job_id == job_id and job["kind"] == "generation":
            try:
                await self.generation_provider.cancel()
            except Exception as error:
                logger.warning("ComfyUI interrupt for job %s failed: %s", job_id, error)
        elif self.active_job_id == job_id and job["kind"] == "upscale" and self.active_upscaler:
            try:
                await self.active_upscaler.cancel()
            except Exception as error:
                logger.warning("Upscaler interrupt for job %s failed: %s", job_id, error)
        if job["kind"] == "upscale":
            provider_id = job["payload"].get("provider", "flashvsr")
            self.repository.upsert_generation_variant(
                job["generation_id"], provider_id, provider_id, "", "cancelled",
                error_message="Upscale cancelled; the original video is unchanged.",
            )
            self.repository.update_generation(
                job["generation_id"],
                status=JobState.COMPLETED,
                progress=1.0,
                stage="Original ready",
                error_message=None,
                error_details=None,
            )
        return self.repository.get_job(job_id)

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                if job_id not in self.cancelled:
                    await self._process(job_id)
            finally:
                self.queue.task_done()

    async def _process(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if not job:
            return
        self.active_job_id = job_id
        try:
            await self._set_state(job_id, JobState.PREPARING, 0.03, "Preparing workflow", started_at=now_iso())
            await self._check_cancelled(job_id)
            if job["kind"] == "generation":
                await self._run_generation(job_id, job)
            elif job["kind"] == "upscale":
                await self._run_upscale(job_id, job)
            else:
                raise RuntimeError(f"Unknown local job type: {job['kind']}")
        except asyncio.CancelledError:
            if job_id in self.cancelled and not self._stopping:
                return
            raise
        except Exception as error:
            await self._fail(job_id, error)
        finally:
            if self.active_job_id == job_id:
                self.active_job_id = None
                self.active_upscaler = None

    async def _run_generation(self, job_id: str, job: dict[str, Any]) -> None:
        generation = self.repository.get_generation(job["generation_id"])
        if not generation:
            raise RuntimeError("Generation metadata could not be found")
        output_dir = self._output_directory(generation)
        parameters = {
            **generation["parameters"],
            "mode": generation["mode"],
            "prompt": generation["prompt"],
            "seed": generation["seed"],
            "references": generation["references"],
        }
        await self._set_state(job_id, JobState.RUNNING, 0.05, "Loading model")
        started_clock = time.perf_counter()

        async def progress(value: float, stage: str) -> None:
            await self._check_cancelled(job_id)
            await self._update_progress(job_id, value, stage)

        artifact = await self.generation_provider.generate(generation["id"], parameters, output_dir, progress)
        source = artifact.path
        await self._set_state(job_id, JobState.POST_PROCESSING, 0.91, "Preparing final output")
        final_output = source
        final_resolution = generation["parameters"].get("final_resolution", "original")
        if artifact.workflow_family == "mock" and final_resolution != "original":
            destination = output_dir / f"{generation['id']}_{final_resolution}.mp4"

            async def post_progress(_value: float, stage: str) -> None:
                await self._check_cancelled(job_id)
                await self._update_progress(job_id, 0.94, stage)

            resized = await self.mock_upscaler.upscale(
                source,
                destination,
                final_resolution,
                post_progress,
                generation["parameters"].get("aspect_ratio", "16:9"),
                generation["seed"],
            )
            final_output = resized.path
        await self._update_progress(job_id, 0.94, "Validating video and native audio")
        output_metadata = await probe_media(
            self.ffprobe,
            source,
            require_audio=artifact.workflow_family != "mock" and bool(parameters.get("audio_enabled", True)),
        )
        output_metadata.update(
            {
                **(artifact.metadata or {}),
                "workflow_family": artifact.workflow_family,
                "model_files": list(artifact.model_files),
                "requested_duration": parameters.get("duration"),
                "seed": generation["seed"],
            }
        )
        if artifact.workflow_family != "mock":
            self._validate_h3_output(output_metadata, parameters)
        await self._update_progress(job_id, 0.97, "Creating thumbnail")
        thumbnail = await create_thumbnail(self.ffmpeg, final_output, output_dir / "thumbnail.jpg")
        completed_at = now_iso()
        execution_seconds = round(time.perf_counter() - started_clock, 3)
        generation = self.repository.update_generation(
            generation["id"],
            original_path=str(source),
            output_path=str(final_output),
            thumbnail_path=str(thumbnail) if thumbnail else None,
            status=JobState.COMPLETED,
            progress=1.0,
            stage="Complete",
            completed_at=completed_at,
            output_metadata_json=json.dumps(output_metadata),
            comfy_prompt_id=artifact.provider_job_id,
            execution_seconds=execution_seconds,
            model_manifest_version=artifact.manifest_version,
        )
        width, height = output_metadata["width"], output_metadata["height"]
        self.repository.add_generation_file(generation["id"], "original", str(source), width, height)
        self.repository.upsert_generation_variant(
            generation["id"],
            "original",
            artifact.workflow_family,
            str(source),
            "completed",
            width=width,
            height=height,
            fps=output_metadata.get("fps"),
            duration=output_metadata.get("duration"),
            audio_present=bool(output_metadata.get("audio_present")),
            metadata=output_metadata,
        )
        if final_output != source:
            self.repository.add_generation_file(generation["id"], f"resize_{final_resolution}", str(final_output))
        if thumbnail:
            self.repository.add_generation_file(generation["id"], "thumbnail", str(thumbnail))
        write_metadata(
            output_dir,
            generation,
            {
                "original": str(source),
                "output": str(final_output),
                "thumbnail": str(thumbnail) if thumbnail else "",
            },
        )
        logger.info(
            "Generation completed job=%s seconds=%.3f output=%s metadata=%s",
            generation["id"], execution_seconds, final_output, output_metadata,
        )
        await self._set_state(job_id, JobState.COMPLETED, 1.0, "Complete", completed_at=completed_at)

    async def _run_upscale(self, job_id: str, job: dict[str, Any]) -> None:
        raw = self.repository.db.fetchone("SELECT * FROM generations WHERE id = ?", (job["generation_id"],))
        if not raw or not raw["original_path"]:
            raise RuntimeError("The original video is unavailable for upscaling.")
        source = Path(raw["original_path"])
        resolution = job["payload"].get("resolution", "1080p")
        provider_id = job["payload"].get("provider", "flashvsr")
        provider = self.upscalers.get(provider_id)
        self.active_upscaler = provider
        generation = self.repository.get_generation(job["generation_id"])
        output_dir = source.parent
        destination = output_dir / f"{job['generation_id']}_{resolution}_{provider_id}.mp4"
        self.repository.upsert_generation_variant(
            job["generation_id"], provider_id, provider_id, str(destination), "upscaling"
        )
        await self._set_state(job_id, JobState.UPSCALING, 0.04, f"Preparing {provider.display_name}")
        started_clock = time.perf_counter()

        async def progress(value: float, stage: str) -> None:
            await self._check_cancelled(job_id)
            await self._update_progress(job_id, value, stage)

        artifact = await provider.upscale(
            source,
            destination,
            resolution,
            progress,
            generation["parameters"].get("aspect_ratio", "16:9") if generation else "16:9",
            generation["seed"] if generation else 0,
        )
        await self._set_state(job_id, JobState.POST_PROCESSING, 0.96, "Recording verified upscale metadata")
        output_metadata = dict((artifact.metadata or {}).get("output", {}))
        execution_seconds = round(time.perf_counter() - started_clock, 3)
        variant_metadata = {
            **(artifact.metadata or {}),
            "execution_seconds": execution_seconds,
            "provider_job_id": artifact.provider_job_id,
        }
        self.repository.upsert_generation_variant(
            job["generation_id"],
            provider_id,
            provider_id,
            str(artifact.path),
            "completed",
            width=output_metadata.get("width"),
            height=output_metadata.get("height"),
            fps=output_metadata.get("fps"),
            duration=output_metadata.get("duration"),
            audio_present=bool(output_metadata.get("audio_present")),
            metadata=variant_metadata,
        )
        self.repository.update_generation(
            job["generation_id"],
            status=JobState.COMPLETED,
            progress=1.0,
            stage=f"{provider.display_name} complete",
            error_message=None,
            error_details=None,
        )
        self.repository.add_generation_file(
            job["generation_id"],
            f"upscale_{provider_id}",
            str(artifact.path),
            output_metadata.get("width"),
            output_metadata.get("height"),
        )
        self.repository.update_job(job_id, execution_metadata_json=json.dumps(variant_metadata))
        refreshed = self.repository.get_generation(job["generation_id"])
        if refreshed:
            variant_rows = self.repository.db.fetchall(
                "SELECT variant, path FROM generation_variants WHERE generation_id = ? AND status = 'completed'",
                (job["generation_id"],),
            )
            output_paths = {str(row["variant"]): str(row["path"]) for row in variant_rows if row["path"]}
            output_paths["original"] = str(source)
            write_metadata(
                output_dir,
                refreshed,
                output_paths,
            )
        logger.info(
            "Upscale completed generation=%s provider=%s seconds=%.3f output=%s metadata=%s",
            job["generation_id"], provider_id, execution_seconds, artifact.path, variant_metadata,
        )
        await self._set_state(job_id, JobState.COMPLETED, 1.0, "Complete", completed_at=now_iso())

    async def _update_progress(self, job_id: str, progress: float, stage: str) -> None:
        current = self.repository.get_job(job_id)
        if not current or current["status"] == JobState.CANCELLED:
            return
        progress = max(float(current["progress"]), progress)
        job = self.repository.update_job(job_id, progress=progress, stage=stage)
        self.repository.update_generation(job["generation_id"], progress=progress, stage=stage)
        await self.broker.publish(job_id, self._public_job(job))

    async def _set_state(
        self, job_id: str, state: JobState, progress: float, stage: str, **extra: Any
    ) -> None:
        current = self.repository.get_job(job_id)
        if not current:
            return
        if current["status"] != state:
            assert_transition(current["status"], state)
        job = self.repository.update_job(job_id, status=state, progress=progress, stage=stage, **extra)
        if job["kind"] == "upscale":
            if state == JobState.COMPLETED:
                generation_state = JobState.COMPLETED
            elif state == JobState.UPSCALE_FAILED:
                generation_state = JobState.UPSCALE_FAILED
            elif state == JobState.CANCELLED:
                generation_state = JobState.COMPLETED
            else:
                generation_state = JobState.UPSCALING
            generation_fields: dict[str, Any] = {
                "status": generation_state,
                "progress": progress,
                "stage": stage,
            }
        else:
            generation_fields = {"status": state, "progress": progress, "stage": stage}
            if "started_at" in extra:
                generation_fields["started_at"] = extra["started_at"]
            if "completed_at" in extra:
                generation_fields["completed_at"] = extra["completed_at"]
        self.repository.update_generation(job["generation_id"], **generation_fields)
        await self.broker.publish(job_id, self._public_job(job))

    async def _check_cancelled(self, job_id: str) -> None:
        if job_id in self.cancelled:
            raise asyncio.CancelledError

    async def _fail(self, job_id: str, error: Exception) -> None:
        job = self.repository.get_job(job_id)
        if not job or job["status"] == JobState.CANCELLED:
            return
        message = self._friendly_error(error)
        details = "".join(traceback.format_exception(error))[-8000:]
        logger.error("Local job %s failed: %s", job_id, details)
        completed_at = now_iso()
        terminal = JobState.UPSCALE_FAILED if job["kind"] == "upscale" else JobState.FAILED
        await self._set_state(
            job_id,
            terminal,
            job["progress"],
            "Upscale failed" if job["kind"] == "upscale" else "Failed",
            error_message=message,
            completed_at=completed_at,
        )
        if job["kind"] == "upscale":
            provider_id = job["payload"].get("provider", "flashvsr")
            self.repository.upsert_generation_variant(
                job["generation_id"], provider_id, provider_id, "", "upscale_failed",
                error_message=message, metadata={"technical_details": details},
            )
            self.repository.update_generation(job["generation_id"], error_message=message, error_details=details)
        else:
            self.repository.update_generation(
                job["generation_id"], error_message=message, error_details=details, completed_at=completed_at
            )

    def _output_directory(self, generation: dict[str, Any]) -> Path:
        created = datetime.fromisoformat(str(generation["created_at"]))
        project = generation.get("project_id") or "unassigned"
        return (
            self.settings.directories["outputs"]
            / f"{created.year:04d}"
            / f"{created.month:02d}"
            / project
            / generation["id"]
        )

    @staticmethod
    def _friendly_error(error: Exception) -> str:
        text = str(error)
        lowered = text.lower()
        if "out of memory" in lowered or "cuda" in lowered and "memory" in lowered:
            return (
                "Not enough GPU memory. Close GPU-heavy applications such as Premiere Pro and try again, "
                "or use the lower-memory profile."
            )
        if "model" in lowered and any(word in lowered for word in ("missing", "not ready", "not installed")):
            if "ref2va" in lowered or "reference" in lowered:
                return "Reference-to-Video models are not installed or verified. Open Models to install or repair them."
            return "A required local AI model is not installed or verified. Open Models to install or repair it."
        if "reference" in lowered and ("too many" in lowered or "at most" in lowered):
            return text
        if "reference" in lowered and any(word in lowered for word in ("decode", "duration", "missing")):
            return text
        if "system ram" in lowered or "gpu memory" in lowered:
            return text
        if "missing nodes" in lowered or "does not support" in lowered:
            return "Your ComfyUI version does not support the installed MiniMax H3 workflow."
        if "local inference engine" in lowered or "comfyui" in lowered and "running" in lowered:
            return "Local inference engine is not running. Check Settings and the ComfyUI log."
        if "ffmpeg" in lowered:
            return "FFmpeg is not installed or configured. Set its path in Settings."
        if "comfyui" in lowered:
            return text
        if "workflow" in lowered:
            return text
        if "upscal" in lowered or "seedvr" in lowered or "flashvsr" in lowered:
            return text
        return "Local processing failed. Open technical details or the logs for more information."

    @staticmethod
    def _parse_dimensions(value: str) -> tuple[int | None, int | None]:
        try:
            width, height = value.lower().replace("×", "x").split("x", 1)
            return int(width), int(height)
        except (TypeError, ValueError):
            return None, None

    @staticmethod
    def _validate_h3_output(metadata: dict[str, Any], parameters: dict[str, Any]) -> None:
        expected_width, expected_height = h3_resolution(
            str(parameters.get("aspect_ratio", "16:9")), str(parameters.get("quality", "high"))
        )
        actual_size = (metadata.get("width"), metadata.get("height"))
        if actual_size != (expected_width, expected_height):
            raise MediaValidationError(
                f"Generated H3 dimensions were {actual_size[0]}x{actual_size[1]}; "
                f"expected {expected_width}x{expected_height}"
            )
        fps = metadata.get("fps")
        if fps is None or abs(float(fps) - 24.0) > 0.05:
            raise MediaValidationError(f"Generated H3 frame rate was {fps}; expected native 24 FPS")
        duration = metadata.get("duration")
        if duration is None or float(duration) <= 0:
            raise MediaValidationError("Generated H3 output did not report a valid duration")

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if key != "payload"}
