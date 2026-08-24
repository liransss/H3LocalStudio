from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.providers.ffmpeg import run_process


async def create_thumbnail(ffmpeg: str | None, source: Path, destination: Path) -> Path | None:
    if not ffmpeg:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    await run_process(
        [ffmpeg, "-y", "-ss", "0.2", "-i", str(source), "-frames:v", "1", "-q:v", "3", str(destination)]
    )
    return destination


def write_metadata(directory: Path, generation: dict[str, Any], files: dict[str, str]) -> Path:
    metadata = {
        "generation_id": generation["id"],
        "project_id": generation["project_id"],
        "prompt": generation["prompt"],
        "references": generation["references"],
        "seed": generation["seed"],
        "mode": generation["mode"],
        **generation["parameters"],
        "timestamps": {
            "created": generation["created_at"],
            "started": generation.get("started_at"),
            "completed": generation.get("completed_at"),
        },
        "mock": generation["is_mock"],
        "files": files,
    }
    path = directory / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return path

