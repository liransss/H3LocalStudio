from __future__ import annotations

from collections import Counter
from typing import Any


REFERENCE_LIMITS = {"image": 9, "video": 3, "audio": 3}
MAX_REFERENCES = 12
FRAME_ROLES = {"first_frame", "last_frame"}


class ReferenceValidationError(ValueError):
    pass


def validate_reference_limits(references: list[dict[str, Any]]) -> None:
    if len(references) > MAX_REFERENCES:
        raise ReferenceValidationError(
            f"Reference-to-Video supports at most {MAX_REFERENCES} combined files; received {len(references)}."
        )
    counts = Counter(str(item.get("media_type", "")) for item in references)
    for media_type, limit in REFERENCE_LIMITS.items():
        if counts[media_type] > limit:
            label = "images" if media_type == "image" else f"{media_type} clips"
            raise ReferenceValidationError(
                f"Reference-to-Video supports at most {limit} {label}; received {counts[media_type]}."
            )


def infer_generation_mode(requested_mode: str, references: list[dict[str, Any]]) -> str:
    validate_reference_limits(references)
    if requested_mode == "t2v":
        if references:
            raise ReferenceValidationError("Text-to-Video does not accept reference media. Choose Auto, Image to Video, or Reference to Video.")
        return "t2v"
    if requested_mode == "i2v":
        _validate_i2v(references)
        return "i2v"
    if requested_mode == "r2v":
        if not references:
            raise ReferenceValidationError("Reference-to-Video needs at least one image, video, or audio reference.")
        return "r2v"
    if requested_mode != "auto":
        raise ReferenceValidationError(f"Unknown generation mode: {requested_mode}")
    if not references:
        return "t2v"
    if (
        len(references) <= 2
        and all(item.get("media_type") == "image" for item in references)
        and all(item.get("role", "general") in FRAME_ROLES for item in references)
    ):
        _validate_i2v(references)
        return "i2v"
    return "r2v"


def _validate_i2v(references: list[dict[str, Any]]) -> None:
    if not 1 <= len(references) <= 2 or any(item.get("media_type") != "image" for item in references):
        raise ReferenceValidationError("Image-to-Video accepts one opening image and an optional ending image only.")
    roles = [str(item.get("role", "general")) for item in references]
    frame_roles = [role for role in roles if role in FRAME_ROLES]
    if frame_roles and len(frame_roles) != len(roles):
        raise ReferenceValidationError("Image-to-Video frame inputs cannot be mixed with semantic reference roles.")
    if len(set(frame_roles)) != len(frame_roles):
        raise ReferenceValidationError("Use only one opening frame and one ending frame.")


def order_i2v_references(references: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    _validate_i2v(references)
    by_role = {item.get("role"): item for item in references if item.get("role") in FRAME_ROLES}
    if by_role:
        first = by_role.get("first_frame") or references[0]
        last = by_role.get("last_frame")
        return first, last
    return references[0], references[1] if len(references) > 1 else None
