from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Protocol

from fastapi import UploadFile

from app.providers.ffmpeg import find_ffprobe
from app.services.file_safety import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, validate_media_path
from app.services.media import create_thumbnail
from app.services.references import validate_reference_limits


MAX_REFERENCE_BYTES = 2 * 1024**3
MIN_TIMED_REFERENCE_SECONDS = 2.0
MAX_TIMED_REFERENCE_SECONDS = 15.0


class AssetRepository(Protocol):
    def get_media_asset(self, asset_id: str) -> dict[str, Any] | None: ...
    def find_media_asset_by_sha256(self, sha256: str) -> dict[str, Any] | None: ...
    def upsert_media_asset(self, asset: dict[str, Any], project_id: str) -> dict[str, Any]: ...


class ReferenceMediaService:
    def __init__(self, data_root: Path, repository: AssetRepository, ffmpeg: str | None):
        self.data_root = data_root
        self.repository = repository
        self.ffmpeg = ffmpeg
        self.ffprobe = find_ffprobe(Path(ffmpeg)) if ffmpeg else None
        self.input_root = data_root / "inputs" / "references"
        self.preview_root = data_root / "inputs" / "reference-previews"
        self.temp_root = data_root / "temp" / "reference-uploads"

    async def ingest(self, upload: UploadFile, project_id: str) -> dict[str, Any]:
        filename = _safe_filename(upload.filename or "reference")
        media_type = _media_type(Path(filename).suffix.lower())
        asset_id = str(uuid.uuid4())
        self.temp_root.mkdir(parents=True, exist_ok=True)
        temporary = self.temp_root / f"{asset_id}{Path(filename).suffix.lower()}"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as target:
                while chunk := await upload.read(8 * 1024 * 1024):
                    size += len(chunk)
                    if size > MAX_REFERENCE_BYTES:
                        raise ValueError("Reference files must be smaller than 2 GiB.")
                    digest.update(chunk)
                    target.write(chunk)
            if not size:
                raise ValueError("The selected reference file is empty.")
            sha256 = digest.hexdigest()
            existing = self.repository.find_media_asset_by_sha256(sha256)
            if existing:
                validate_media_path(Path(existing["path"]), existing["media_type"])
                return self.repository.upsert_media_asset(existing, project_id)

            probe = await self._probe(temporary, media_type)
            destination = self.input_root / sha256[:2] / f"{sha256}{Path(filename).suffix.lower()}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination)
            preview_path: Path | None = None
            if media_type == "image":
                preview_path = destination
            elif media_type == "video" and self.ffmpeg:
                preview_path = self.preview_root / f"{asset_id}.jpg"
                await create_thumbnail(self.ffmpeg, destination, preview_path)
            asset = {
                "id": asset_id,
                "sha256": sha256,
                "filename": filename,
                "media_type": media_type,
                "path": str(destination),
                "preview_path": str(preview_path) if preview_path else None,
                "size_bytes": size,
                "duration": probe.get("duration"),
                "width": probe.get("width"),
                "height": probe.get("height"),
                "audio_present": bool(probe.get("audio_present")),
                "metadata": probe,
            }
            return self.repository.upsert_media_asset(asset, project_id)
        finally:
            await upload.close()
            temporary.unlink(missing_ok=True)

    def resolve_generation_references(
        self, references: list[dict[str, Any]], project_id: str
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for order, requested in enumerate(references):
            asset_id = str(requested.get("asset_id") or "")
            asset = self.repository.get_media_asset(asset_id) if asset_id else None
            if not asset:
                raise ValueError("A selected reference is no longer available. Remove it and add the file again.")
            validate_media_path(Path(asset["path"]), asset["media_type"])
            self.repository.upsert_media_asset(asset, project_id)
            role = str(requested.get("role") or "general")
            resolved.append(
                {
                    **asset,
                    "asset_id": asset["id"],
                    "role": role,
                    "notes": str(requested.get("notes") or "").strip()[:500],
                    "order": order,
                    "content_url": f"/api/reference-assets/{asset['id']}/content",
                    "preview_url": f"/api/reference-assets/{asset['id']}/preview" if asset.get("preview_path") else None,
                }
            )
        validate_reference_limits(resolved)
        return resolved

    async def _probe(self, path: Path, media_type: str) -> dict[str, Any]:
        if not self.ffprobe or not self.ffmpeg:
            raise ValueError("FFmpeg and FFprobe are required to validate reference media.")
        payload = await asyncio.to_thread(_probe_payload, self.ffprobe, path)
        streams = payload.get("streams", [])
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if media_type in {"image", "video"} and not video_stream:
            raise ValueError(f"The selected {media_type} file does not contain a decodable video stream.")
        if media_type == "audio" and not audio_stream:
            raise ValueError("The selected audio file does not contain a decodable audio stream.")
        duration = _duration(payload, video_stream if media_type == "video" else audio_stream)
        if media_type in {"video", "audio"}:
            if duration is None:
                raise ValueError(f"The {media_type} duration could not be read.")
            if not MIN_TIMED_REFERENCE_SECONDS <= duration <= MAX_TIMED_REFERENCE_SECONDS:
                raise ValueError(
                    f"Reference {media_type} clips must be between {MIN_TIMED_REFERENCE_SECONDS:g} and "
                    f"{MAX_TIMED_REFERENCE_SECONDS:g} seconds; this file is {duration:.2f} seconds."
                )
        await asyncio.to_thread(_decode_sample, self.ffmpeg, path, media_type)
        return {
            "duration": round(duration, 6) if duration is not None else None,
            "width": int(video_stream.get("width")) if video_stream and video_stream.get("width") else None,
            "height": int(video_stream.get("height")) if video_stream and video_stream.get("height") else None,
            "audio_present": audio_stream is not None,
            "video_codec": video_stream.get("codec_name") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "sample_rate": int(audio_stream["sample_rate"]) if audio_stream and audio_stream.get("sample_rate") else None,
            "channels": int(audio_stream["channels"]) if audio_stream and audio_stream.get("channels") else None,
            "format_name": payload.get("format", {}).get("format_name"),
        }


def public_media_asset(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        **asset,
        "content_url": f"/api/reference-assets/{asset['id']}/content",
        "preview_url": f"/api/reference-assets/{asset['id']}/preview" if asset.get("preview_path") else None,
    }


def _safe_filename(filename: str) -> str:
    leaf = Path(filename).name.strip() or "reference"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(leaf).stem).strip(" ._") or "reference"
    return f"{stem[:120]}{Path(leaf).suffix.lower()}"


def _media_type(extension: str) -> str:
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError("Unsupported reference file. Use PNG/JPG/WEBP, MP4/MOV/WEBM/MKV, or WAV/MP3/M4A/FLAC.")


def _probe_payload(ffprobe: str, path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height,duration,sample_rate,channels:format=duration,format_name,size",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError("The reference file could not be read by FFprobe.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("FFprobe returned invalid reference metadata.") from error


def _decode_sample(ffmpeg: str, path: Path, media_type: str) -> None:
    map_value = "0:a:0" if media_type == "audio" else "0:v:0"
    arguments = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", map_value]
    if media_type == "audio":
        arguments.extend(["-t", "1"])
    else:
        arguments.extend(["-frames:v", "1"])
    arguments.extend(["-f", "null", "NUL"])
    result = subprocess.run(
        arguments,
        capture_output=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError(f"The reference {media_type} could not be decoded by FFmpeg.")


def _duration(payload: dict[str, Any], stream: dict[str, Any] | None) -> float | None:
    for value in ((stream or {}).get("duration"), payload.get("format", {}).get("duration")):
        try:
            if value not in {None, "", "N/A"}:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None
