from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.jobs.state import assert_transition
from app.models.schemas import GenerationCreate
from app.models.upscaler_manifest import UPSCALER_MANIFEST
from app.providers.upscalers import _fit_dimensions, _validate_upscaled_media
from app.services.ffprobe import MediaValidationError
from app.services.upscaler_model_store import UpscalerModelStore
from app.workflows.upscale import build_flashvsr_workflow, build_seedvr2_workflow


def test_upscaler_manifest_is_pinned_and_uses_standard_comfy_paths(tmp_path) -> None:
    UPSCALER_MANIFEST.validate()
    flash_files = UPSCALER_MANIFEST.family_files("flashvsr")
    seed_files = UPSCALER_MANIFEST.family_files("seedvr2")
    assert len(flash_files) == 4
    assert len(seed_files) == 2
    assert UPSCALER_MANIFEST.family_size("flashvsr") == 6_948_393_553
    assert UPSCALER_MANIFEST.family_size("seedvr2") == 3_959_584_518
    assert all(len(item.sha256) == 64 for item in (*flash_files, *seed_files))
    assert all(item.revision == "27561b186ded3402d7c975f4fd722e2885b6135f" for item in flash_files)
    assert all(item.revision == "673340c8a66db62b84e4099def7d01d337ae12dc" for item in seed_files)

    store = UpscalerModelStore(tmp_path / "ComfyUI", tmp_path / "cache", managed_runtime=True)
    assert store.path_for(UPSCALER_MANIFEST.component("flash_diffusion")) == (
        tmp_path / "ComfyUI" / "models" / "FlashVSR-v1.1" / "diffusion_pytorch_model_streaming_dmd.safetensors"
    )
    assert store.path_for(UPSCALER_MANIFEST.component("seedvr2_diffusion")) == (
        tmp_path / "ComfyUI" / "models" / "diffusion_models" / "seedvr2_3b_int8_convrot.safetensors"
    )


def test_flashvsr_workflow_uses_16gb_safe_sdpa_profile_and_native_audio() -> None:
    workflow = build_flashvsr_workflow("input.mp4", "phase3/flash", 42)
    init = workflow.prompt["3"]["inputs"]
    upscale = workflow.prompt["4"]["inputs"]
    assert workflow.provider_id == "flashvsr"
    assert init["model"] == "FlashVSR-v1.1"
    assert init["mode"] == "tiny"
    assert init["attention_mode"] == "sdpa"
    assert init["force_offload"] is True
    assert upscale["tiled_vae"] is True
    assert upscale["tiled_dit"] is True
    assert upscale["tile_size"] == 384
    assert upscale["frame_chunk_size"] == 21
    assert upscale["keep_models_on_cpu"] is True
    assert upscale["resize_factor"] == 0.75
    assert workflow.prompt["5"]["inputs"]["audio"] == ["2", 1]
    assert workflow.prompt["5"]["inputs"]["fps"] == ["2", 2]


def test_seedvr2_workflow_uses_native_int8_one_step_temporal_chunks() -> None:
    workflow = build_seedvr2_workflow("input.mp4", "phase3/seed", 99, 1890, 1080)
    assert workflow.provider_id == "seedvr2"
    assert workflow.prompt["3"]["inputs"]["width"] == 1890
    assert workflow.prompt["3"]["inputs"]["height"] == 1080
    assert workflow.prompt["6"]["inputs"]["unet_name"] == "seedvr2_3b_int8_convrot.safetensors"
    assert workflow.prompt["8"]["inputs"]["chunking_mode"] == "auto"
    assert workflow.prompt["10"]["inputs"]["steps"] == 1
    assert workflow.prompt["10"]["inputs"]["sampler_name"] == "euler"
    assert workflow.prompt["10"]["inputs"]["scheduler"] == "simple"
    assert workflow.prompt["14"]["inputs"]["audio"] == ["2", 1]


def test_1080p_fit_and_media_validation_preserve_timing_and_audio() -> None:
    assert _fit_dimensions(1344, 768, 1920, 1080) == (1890, 1080)
    source = {"duration": 4.458333, "audio_present": True}
    output = {"width": 1920, "height": 1080, "fps": 24.0, "duration": 4.458333, "audio_present": True}
    _validate_upscaled_media(output, source, 1920, 1080)
    with pytest.raises(MediaValidationError):
        _validate_upscaled_media({**output, "audio_present": False}, source, 1920, 1080)
    with pytest.raises(MediaValidationError):
        _validate_upscaled_media({**output, "fps": 30.0}, source, 1920, 1080)
    with pytest.raises(MediaValidationError):
        _validate_upscaled_media({**output, "duration": 4.375}, source, 1920, 1080)


def test_upscaler_downloads_require_explicit_size_confirmation(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/models/install", json={"family": "flashvsr", "confirmed": False})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["total_size"] == UPSCALER_MANIFEST.family_size("flashvsr")
        assert detail["files"] == [item.filename for item in UPSCALER_MANIFEST.family_files("flashvsr")]


def test_upscale_variants_persist_independently_from_original(repository, tmp_path) -> None:
    generation = repository.create_generation(GenerationCreate(prompt="phase 3"), 123, "t2v", False)
    original = tmp_path / f"{generation['id']}_original.mp4"
    repository.update_generation(
        generation["id"],
        status="completed",
        original_path=str(original),
        output_path=str(original),
        output_metadata_json='{"width": 1344, "height": 768, "fps": 24, "duration": 4.458333, "audio_present": true}',
    )
    repository.upsert_generation_variant(
        generation["id"],
        "flashvsr",
        "flashvsr",
        "",
        "upscale_failed",
        error_message="fixture failure",
    )
    saved = repository.get_generation(generation["id"])
    assert saved["status"] == "completed"
    assert saved["original_url"].endswith("/original")
    original_variant = next(item for item in saved["variants"] if item["variant"] == "original")
    failed_variant = next(item for item in saved["variants"] if item["variant"] == "flashvsr")
    assert original_variant["status"] == "completed"
    assert failed_variant["status"] == "upscale_failed"
    assert failed_variant["url"] is None


def test_phase3_upscale_state_transitions_are_terminal() -> None:
    assert_transition("preparing", "upscaling")
    assert_transition("upscaling", "post-processing")
    assert_transition("upscaling", "upscale_failed")
    with pytest.raises(ValueError):
        assert_transition("upscale_failed", "upscaling")
