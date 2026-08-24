from __future__ import annotations

from pathlib import Path
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.jobs.manager import JobManager
from app.models.h3_manifest import H3_MANIFEST, H3ModelFile, H3ModelManifest
from app.providers.comfyui import ComfyUIClient, parse_output_descriptor
from app.services.ffprobe import MediaValidationError, parse_ffprobe_payload
from app.services.h3_parameters import h3_frame_count, h3_resolution
from app.services.model_store import H3ModelStore
from app.services.model_downloads import ModelDownloadManager
from app.workflows.h3_t2v import build_h3_t2v_workflow


def test_manifest_is_pinned_and_valid() -> None:
    H3_MANIFEST.validate()
    files = H3_MANIFEST.family_files("fl2va")
    assert len(files) == 5
    assert all(item.repo == "Comfy-Org/MiniMax-H3" for item in files)
    assert all(len(item.sha256) == 64 and item.size > 1_000_000 for item in files)
    assert H3_MANIFEST.component("fl2va_diffusion").filename == "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    assert H3_MANIFEST.component("fl2va_diffusion").url.endswith(
        "/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    )


def test_model_paths_use_standard_comfyui_layout(tmp_path: Path) -> None:
    store = H3ModelStore(tmp_path / "ComfyUI", tmp_path / "cache")
    component = H3_MANIFEST.component("audio_vae")
    assert store.path_for(component) == tmp_path / "ComfyUI" / "models" / "vae" / component.filename
    assert store.family_status("fl2va")["ready"] is False


@pytest.mark.asyncio
async def test_model_download_is_atomic_and_verified(tmp_path: Path) -> None:
    content = b"small deterministic model fixture"
    component = H3ModelFile(
        id="fixture",
        filename="fixture.safetensors",
        model_dir="vae",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        repo="Comfy-Org/fixture",
        revision="abc123",
        compatible_families=("fl2va",),
    )
    manifest = H3ModelManifest("test", "Comfy-Org/workflows", "abc123", (component,), {"fl2va": ("fixture",)})
    store = H3ModelStore(tmp_path / "ComfyUI", tmp_path / "cache", manifest)
    manager = ModelDownloadManager(
        store,
        httpx.MockTransport(lambda _request: httpx.Response(200, content=content)),
    )
    operation = manager.start_install("fl2va")
    await manager.tasks[operation["id"]]
    destination = store.path_for(component)
    assert destination.read_bytes() == content
    assert not destination.with_name(f"{destination.name}.part").exists()
    assert store.component_status(component)["status"] == "verified"


@pytest.mark.parametrize(
    ("seconds", "frames"),
    [(4, 107), (5, 124), (8, 192), (10, 243), (15, 362)],
)
def test_duration_maps_to_h3_17k_plus_5_grid(seconds: int, frames: int) -> None:
    assert h3_frame_count(seconds) == frames
    assert frames % 17 == 5


def test_h3_resolution_mapping() -> None:
    assert h3_resolution("16:9", "high") == (1344, 768)
    assert h3_resolution("16:9", "preview") == (736, 416)
    assert h3_resolution("9:16", "high") == (768, 1344)
    assert all(value % 32 == 0 for value in h3_resolution("21:9", "high"))


def test_api_workflow_injects_only_requested_fields() -> None:
    prompt = "镜头推进\nDialogue: שלום עולם\nSFX: rain"
    workflow = build_h3_t2v_workflow(
        {
            "prompt": prompt,
            "seed": 987654321,
            "duration": 4,
            "aspect_ratio": "16:9",
            "quality": "preview",
            "steps": 20,
            "turbo": True,
            "audio_enabled": True,
        }
    )
    assert workflow.prompt["5"]["inputs"]["prompt"] == prompt
    assert workflow.prompt["6"]["inputs"]["noise_seed"] == 987654321
    assert workflow.prompt["5"]["inputs"]["length"] == 107
    assert workflow.prompt["5"]["inputs"]["width"] == 736
    assert workflow.prompt["8"]["inputs"]["steps"] == 8
    assert workflow.prompt["10"]["class_type"] == "LoraLoaderModelOnly"
    assert workflow.prompt["7"]["inputs"]["sampler_name"] == "res_multistep"
    assert workflow.prompt["8"]["inputs"]["scheduler"] == "simple"
    assert workflow.prompt["14"]["inputs"]["audio"] == ["13", 0]
    assert workflow.prompt["15"]["class_type"] == "SaveVideo"
    assert workflow.prompt["15"]["inputs"]["format"] == "mp4"
    assert workflow.prompt["15"]["inputs"]["codec"] == "auto"


def test_workflow_can_disable_audio_and_turbo() -> None:
    workflow = build_h3_t2v_workflow({"prompt": "test", "seed": 1, "duration": 5, "audio_enabled": False})
    assert "10" not in workflow.prompt
    assert "13" not in workflow.prompt
    assert "audio" not in workflow.prompt["14"]["inputs"]
    assert workflow.steps == 20


def test_history_output_parsing_prefers_save_video_node() -> None:
    history = {
        "prompt-1": {
            "outputs": {
                "12": {"images": [{"filename": "preview.png", "subfolder": "", "type": "temp"}]},
                "15": {"images": [{"filename": "H3_00001_.mp4", "subfolder": "H3LocalStudio", "type": "output"}]},
            }
        }
    }
    assert parse_output_descriptor(history, "prompt-1", "15") == {
        "filename": "H3_00001_.mp4",
        "subfolder": "H3LocalStudio",
        "type": "output",
    }


def test_ffprobe_metadata_parsing_and_audio_requirement() -> None:
    payload = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 736, "height": 416, "avg_frame_rate": "24/1"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"duration": "4.458", "format_name": "mov,mp4", "size": "123456"},
    }
    metadata = parse_ffprobe_payload(payload, require_audio=True)
    assert metadata["fps"] == 24
    assert metadata["audio_present"] is True
    assert metadata["sample_rate"] == 48000
    with pytest.raises(MediaValidationError):
        parse_ffprobe_payload({"streams": [payload["streams"][0]], "format": {}}, require_audio=True)
    JobManager._validate_h3_output(
        {"width": 736, "height": 416, "fps": 24.0, "duration": 4.458},
        {"aspect_ratio": "16:9", "quality": "preview"},
    )
    with pytest.raises(MediaValidationError):
        JobManager._validate_h3_output(
            {"width": 736, "height": 416, "fps": 30.0, "duration": 4.458},
            {"aspect_ratio": "16:9", "quality": "preview"},
        )


@pytest.mark.asyncio
async def test_comfyui_http_responses_are_parsed(tmp_path: Path) -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.33.1"}})
        if request.url.path == "/object_info":
            return httpx.Response(200, json={"SaveVideo": {}, "MiniMaxH3ImageToVideo": {}})
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "prompt-1", "number": 1, "node_errors": {}})
        if request.url.path == "/history/prompt-1":
            return httpx.Response(200, json={"prompt-1": {"outputs": {}}})
        if request.url.path == "/view":
            return httpx.Response(200, content=b"real-video-bytes")
        if request.url.path in {"/queue", "/interrupt"}:
            return httpx.Response(200, json={})
        return httpx.Response(404)

    client = ComfyUIClient("http://127.0.0.1:8188", httpx.MockTransport(handler))
    assert (await client.health())["compatible"] is True
    await client.validate_nodes({"SaveVideo", "MiniMaxH3ImageToVideo"})
    assert await client._queue_prompt({"1": {}}, "client-1") == "prompt-1"
    assert "prompt-1" in await client.history("prompt-1")
    output = await client.download_output(
        {"filename": "video.mp4", "subfolder": "", "type": "output"}, tmp_path / "video.mp4"
    )
    assert output.read_bytes() == b"real-video-bytes"
    await client.cancel_prompt("prompt-1")
    assert ("POST", "/queue") in requests
    assert ("POST", "/interrupt") in requests


def test_reference_modes_require_valid_assets_while_mock_t2v_remains_independent(tmp_path: Path) -> None:
    real_settings = AppSettings(
        data_root=tmp_path / "real",
        config_path=tmp_path / "real.json",
        mock_mode=False,
    )
    with TestClient(create_app(real_settings)) as client:
        response = client.post("/api/generations", json={"prompt": "reference mode", "mode": "i2v", "duration": 4})
        assert response.status_code == 422

    mock_settings = AppSettings(
        data_root=tmp_path / "mock",
        config_path=tmp_path / "mock.json",
        mock_mode=True,
        mock_step_delay=0,
    )
    with TestClient(create_app(mock_settings)) as client:
        response = client.post("/api/generations", json={"prompt": "mock mode", "mode": "t2v"})
        assert response.status_code == 202


def test_model_download_requires_explicit_confirmation(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/models/install", json={"family": "fl2va", "confirmed": False})
        assert response.status_code == 409
        assert response.json()["detail"]["total_size"] == H3_MANIFEST.family_size("fl2va")
        assert len(response.json()["detail"]["files"]) == 5
