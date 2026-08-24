from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

from app.providers.base import ProgressCallback, UpscaleArtifact, UpscalerAvailability, VideoUpscalerProvider


class FFmpegUnavailable(RuntimeError):
    pass


def find_ffmpeg(configured_path: Path | None = None) -> str | None:
    if configured_path and configured_path.is_file():
        return str(configured_path)
    return shutil.which("ffmpeg")


def find_ffprobe(configured_ffmpeg_path: Path | None = None) -> str | None:
    if configured_ffmpeg_path and configured_ffmpeg_path.is_file():
        sibling = configured_ffmpeg_path.with_name("ffprobe.exe" if configured_ffmpeg_path.suffix else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe")


async def run_process(arguments: list[str]) -> None:
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    communicate = asyncio.create_task(asyncio.to_thread(process.communicate))
    try:
        _, stderr = await asyncio.shield(communicate)
    except asyncio.CancelledError:
        process.terminate()
        try:
            await asyncio.wait_for(asyncio.shield(communicate), timeout=10)
        except TimeoutError:
            process.kill()
            await communicate
        raise
    if process.returncode != 0:
        details = stderr.decode(errors="replace")[-4000:]
        raise RuntimeError(f"FFmpeg processing failed.\n{details}")


class FFmpegUpscaler(VideoUpscalerProvider):
    """Stable local Lanczos resize provider. It is deliberately not labeled as AI upscaling."""

    DIMENSIONS = {"1080p": (1920, 1080), "1440p": (2560, 1440), "4k": (3840, 2160)}
    provider_id = "ffmpeg_resize"
    display_name = "FFmpeg Lanczos resize"

    def __init__(self, executable: str | None):
        self.executable = executable

    async def availability(self) -> UpscalerAvailability:
        return UpscalerAvailability(
            self.provider_id, self.display_name, bool(self.executable), True, bool(self.executable),
            None if self.executable else "FFmpeg is not installed or configured.", None,
        )

    def required_models(self) -> tuple[str, ...]:
        return ()

    async def install(self, *, confirmed: bool, repair: bool = False) -> dict[str, object]:
        return {"installed": bool(self.executable), "provider": self.provider_id, "repair": repair, "confirmed": confirmed}

    async def validate(self) -> UpscalerAvailability:
        return await self.availability()

    async def upscale(
        self,
        source: Path,
        destination: Path,
        resolution: str,
        progress: ProgressCallback,
        aspect_ratio: str = "16:9",
        seed: int = 0,
    ) -> UpscaleArtifact:
        if not self.executable:
            raise FFmpegUnavailable("FFmpeg is not installed or configured.")
        if resolution not in self.DIMENSIONS:
            raise ValueError(f"Unsupported final resolution: {resolution}")
        width, height = self._target_dimensions(resolution, aspect_ratio)
        await progress(0.84, f"Resizing to {width} × {height}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await run_process(
            [
                self.executable,
                "-y",
                "-i",
                str(source),
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",
                str(destination),
            ]
        )
        return UpscaleArtifact(destination, self.provider_id, self.display_name, metadata={"seed": seed, "kind": "resize"})

    @classmethod
    def _target_dimensions(cls, resolution: str, aspect_ratio: str) -> tuple[int, int]:
        width, height = cls.DIMENSIONS[resolution]
        if aspect_ratio == "9:16":
            return height, width
        if aspect_ratio == "1:1":
            return height, height
        if aspect_ratio == "4:3":
            return int(height * 4 / 3), height
        if aspect_ratio == "3:4":
            return height, int(height * 4 / 3)
        if aspect_ratio == "21:9":
            return int(round(height * 21 / 9 / 2) * 2), height
        return width, height


async def finalize_ai_upscale(
    executable: str | None,
    ai_video: Path,
    original: Path,
    destination: Path,
    width: int,
    height: int,
    duration: float,
    progress: ProgressCallback,
) -> Path:
    if not executable:
        raise FFmpegUnavailable("FFmpeg is required to finalize the AI-upscaled video.")
    await progress(0.91, "Encoding H.264 and restoring original audio")
    destination.parent.mkdir(parents=True, exist_ok=True)
    await run_process(
        [
            executable,
            "-y",
            "-i",
            str(ai_video),
            "-i",
            str(original),
            "-filter_complex",
            f"[0:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=24,"
            f"tpad=stop_mode=clone:stop_duration={duration:.6f},"
            f"trim=duration={duration:.6f},setpts=PTS-STARTPTS[v]",
            "-map",
            "[v]",
            "-map",
            "1:a?",
            "-r",
            "24",
            "-fps_mode",
            "cfr",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-t",
            f"{duration:.6f}",
            str(destination),
        ]
    )
    return destination
