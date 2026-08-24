from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}


class UnsafePathError(ValueError):
    pass


def ensure_within_root(candidate: Path, root: Path) -> Path:
    resolved_candidate = candidate.expanduser().resolve()
    resolved_root = root.expanduser().resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise UnsafePathError(f"Path is outside the permitted local storage root: {resolved_candidate}") from error
    return resolved_candidate


def validate_media_path(path: Path, media_type: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError("The selected reference file no longer exists")
    allowed = {
        "image": IMAGE_EXTENSIONS,
        "video": VIDEO_EXTENSIONS,
        "audio": AUDIO_EXTENSIONS,
    }.get(media_type)
    if allowed is None or resolved.suffix.lower() not in allowed:
        raise ValueError(f"Unsupported {media_type} file format")
    return resolved

