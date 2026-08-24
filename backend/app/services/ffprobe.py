from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any


class MediaValidationError(RuntimeError):
    pass


def parse_ffprobe_payload(payload: dict[str, Any], *, require_audio: bool = False) -> dict[str, Any]:
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if video is None:
        raise MediaValidationError("Generated output is corrupt or does not contain a video stream")
    if require_audio and audio is None:
        raise MediaValidationError("MiniMax H3 output did not contain the requested native audio stream")
    format_info = payload.get("format") or {}
    duration_value = video.get("duration") or format_info.get("duration")
    metadata: dict[str, Any] = {
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "duration": float(duration_value) if duration_value not in {None, "N/A"} else None,
        "video_codec": video.get("codec_name"),
        "audio_present": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio and str(audio.get("sample_rate", "")).isdigit() else None,
        "channels": int(audio["channels"]) if audio and audio.get("channels") is not None else None,
        "container": format_info.get("format_name"),
        "size": int(format_info["size"]) if str(format_info.get("size", "")).isdigit() else None,
    }
    if metadata["width"] <= 0 or metadata["height"] <= 0:
        raise MediaValidationError("Generated output reported invalid video dimensions")
    return metadata


async def probe_media(ffprobe: str | None, source: Path, *, require_audio: bool = False) -> dict[str, Any]:
    if not ffprobe:
        raise MediaValidationError("FFprobe is required to validate real MiniMax H3 output")
    result = await asyncio.to_thread(
        subprocess.run,
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration,sample_rate,channels:format=duration,format_name,size",
            "-of", "json",
            str(source),
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise MediaValidationError(f"FFprobe could not read the generated video: {result.stderr.decode(errors='replace')[-2000:]}")
    try:
        return parse_ffprobe_payload(json.loads(result.stdout), require_audio=require_audio)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise MediaValidationError(f"FFprobe returned invalid media metadata: {error}") from error


def _fraction(value: Any) -> float | None:
    if value in {None, "", "0/0", "N/A"}:
        return None
    try:
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/", 1)
            return float(numerator) / float(denominator)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
