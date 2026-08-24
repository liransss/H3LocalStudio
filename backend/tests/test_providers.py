from app.providers.comfyui import is_compatible_version
from app.providers.ffmpeg import FFmpegUpscaler


def test_comfyui_minimum_version():
    assert is_compatible_version("0.30.0") is True
    assert is_compatible_version("0.29.9") is False
    assert is_compatible_version("0.41.2+build") is True
    assert is_compatible_version(None) is None


def test_aspect_aware_output_dimensions():
    assert FFmpegUpscaler._target_dimensions("1080p", "16:9") == (1920, 1080)
    assert FFmpegUpscaler._target_dimensions("1080p", "9:16") == (1080, 1920)
    assert FFmpegUpscaler._target_dimensions("1080p", "1:1") == (1080, 1080)
    assert FFmpegUpscaler._target_dimensions("1080p", "21:9") == (2520, 1080)
