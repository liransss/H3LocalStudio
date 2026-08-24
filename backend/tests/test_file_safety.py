from pathlib import Path

import pytest

from app.services.file_safety import UnsafePathError, ensure_within_root


def test_path_inside_root_is_allowed(tmp_path: Path):
    target = tmp_path / "outputs" / "clip.mp4"
    assert ensure_within_root(target, tmp_path) == target.resolve()


def test_path_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(UnsafePathError):
        ensure_within_root(tmp_path / ".." / "secret.mp4", tmp_path)

