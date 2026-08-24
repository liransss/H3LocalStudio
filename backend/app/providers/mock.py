from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.providers.base import GenerationArtifact, ProgressCallback, VideoGenerationProvider
from app.providers.ffmpeg import FFmpegUnavailable, run_process


class MockVideoProvider(VideoGenerationProvider):
    STAGES = (
        (0.08, "Preparing workflow"),
        (0.18, "Loading model"),
        (0.28, "Encoding prompt"),
        (0.62, "Generating video"),
        (0.76, "Decoding video"),
        (0.86, "Preserving native audio"),
    )

    def __init__(self, ffmpeg: str | None, step_delay: float = 0.45, should_fail: bool = False):
        self.ffmpeg = ffmpeg
        self.step_delay = step_delay
        self.should_fail = should_fail

    async def generate(
        self, generation_id: str, parameters: dict[str, Any], output_dir: Path, progress: ProgressCallback
    ) -> GenerationArtifact:
        for value, stage in self.STAGES:
            await progress(value, stage)
            await asyncio.sleep(self.step_delay)
        if self.should_fail:
            raise RuntimeError("Mock Mode simulated a generation failure.")
        if not self.ffmpeg:
            raise FFmpegUnavailable(
                "FFmpeg is required to create the local Mock Mode preview. Configure it in Settings."
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{generation_id}_original.mp4"
        duration = min(float(parameters.get("duration", 5)), 3.0)
        fps = int(parameters.get("fps", 24))
        dimensions = parameters.get("generation_resolution", "1344x768").replace("×", "x")
        if "x" not in dimensions:
            dimensions = "1344x768"
        await run_process(
            [
                self.ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x111426:s={dimensions}:r={fps}:d={duration}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=220:sample_rate=48000:duration={duration}",
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(destination),
            ]
        )
        await progress(0.9, "Encoding final video")
        return GenerationArtifact(path=destination, workflow_family="mock")
