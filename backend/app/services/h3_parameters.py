from __future__ import annotations

import math


H3_FPS = 24
H3_MIN_DURATION = 4.0
H3_MAX_DURATION = 15.0
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "21:9": (21, 9),
}
QUALITY_MEGAPIXELS = {"preview": 0.30, "high": 0.98}


def h3_frame_count(duration_seconds: float) -> int:
    if not H3_MIN_DURATION <= duration_seconds <= H3_MAX_DURATION:
        raise ValueError(f"H3 duration must be between {H3_MIN_DURATION:g} and {H3_MAX_DURATION:g} seconds")
    requested = math.floor(duration_seconds * H3_FPS + 0.5)
    return requested + (5 - requested % 17) % 17


def h3_resolution(aspect_ratio: str, quality: str) -> tuple[int, int]:
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")
    if quality not in QUALITY_MEGAPIXELS:
        raise ValueError(f"Unsupported H3 quality: {quality}")
    numerator, denominator = ASPECT_RATIOS[aspect_ratio]
    ratio = numerator / denominator
    target_area = QUALITY_MEGAPIXELS[quality] * 1024 * 1024
    width = round(math.sqrt(target_area * ratio) / 32) * 32
    height = round(math.sqrt(target_area / ratio) / 32) * 32
    return max(32, width), max(32, height)


def normalize_h3_parameters(parameters: dict[str, object]) -> dict[str, object]:
    duration = float(parameters.get("duration", 5))
    aspect_ratio = str(parameters.get("aspect_ratio", "16:9"))
    quality = str(parameters.get("quality", "high"))
    width, height = h3_resolution(aspect_ratio, quality)
    normalized = dict(parameters)
    normalized.update(
        {
            "duration": duration,
            "fps": H3_FPS,
            "frame_count": h3_frame_count(duration),
            "width": width,
            "height": height,
            "generation_resolution": f"{width}x{height}",
        }
    )
    return normalized
