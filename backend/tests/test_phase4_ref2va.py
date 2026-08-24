from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models.h3_manifest import H3_MANIFEST
from app.models.schemas import GenerationCreate, MediaReference, ProjectCreate
from app.services.file_safety import validate_media_path
from app.services.reference_media import _media_type
from app.services.references import ReferenceValidationError, infer_generation_mode, validate_reference_limits
from app.workflows.h3_ref2va import H3Ref2VAWorkflowAdapter
from app.workflows.h3_t2v import build_h3_t2v_workflow


def _reference(asset_id: str, media_type: str, order: int, **extra: object) -> dict[str, object]:
    return {
        "id": asset_id,
        "asset_id": asset_id,
        "filename": f"{asset_id}.{ {'image': 'png', 'video': 'mp4', 'audio': 'wav'}[media_type] }",
        "media_type": media_type,
        "role": "general",
        "notes": "",
        "order": order,
        "comfyui_path": f"H3LocalStudio/ref2va/job/{asset_id}",
        "audio_present": False,
        **extra,
    }


def test_ref2va_manifest_reuses_shared_components() -> None:
    H3_MANIFEST.validate()
    fl2va_ids = {item.id for item in H3_MANIFEST.family_files("fl2va")}
    ref2va = H3_MANIFEST.family_files("ref2va")
    shared = {item.id for item in ref2va if "fl2va" in item.compatible_families}
    specific = {item.id for item in ref2va if item.compatible_families == ("ref2va",)}
    assert shared == {"text_encoder", "video_vae", "audio_vae"}
    assert specific == {"ref2va_diffusion", "ref2va_turbo_lora"}
    assert shared <= fl2va_ids
    assert sum(item.size for item in ref2va if item.id in specific) == 22_926_572_616


def test_auto_mode_inference_and_reference_limits() -> None:
    assert infer_generation_mode("auto", []) == "t2v"
    assert infer_generation_mode("auto", [_reference("opening", "image", 0, role="first_frame")]) == "i2v"
    assert infer_generation_mode("auto", [_reference("character", "image", 0, role="character")]) == "r2v"
    assert infer_generation_mode("auto", [_reference("motion", "video", 0)]) == "r2v"
    with pytest.raises(ReferenceValidationError, match="at most 9"):
        validate_reference_limits([_reference(f"image-{index}", "image", index) for index in range(10)])
    with pytest.raises(ReferenceValidationError, match="at most 3"):
        validate_reference_limits([_reference(f"audio-{index}", "audio", index) for index in range(4)])


def test_ref2va_workflow_injects_ordered_multimodal_fields_and_roles() -> None:
    references = [
        _reference("character", "image", 0, role="character", notes="Keep the silver face markings"),
        _reference("motion", "video", 1, role="motion", audio_present=True),
        _reference("voice", "audio", 2, role="voice"),
    ]
    workflow = H3Ref2VAWorkflowAdapter().build(
        {
            "prompt": "The character runs through rain and speaks clearly.",
            "references": references,
            "duration": 4,
            "quality": "preview",
            "aspect_ratio": "16:9",
            "seed": 123,
            "turbo": True,
            "audio_enabled": True,
        }
    )
    conditioning = workflow.prompt["5"]
    assert conditioning["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert conditioning["inputs"]["ref_images.ref_image_0"] == ["20", 0]
    assert conditioning["inputs"]["ref_videos.ref_video_0"] == ["22", 0]
    assert conditioning["inputs"]["ref_video_audios.ref_video_audio_0"] == ["22", 1]
    assert conditioning["inputs"]["ref_audios.ref_audio_0"] == ["23", 0]
    assert "1. <Picture 1>: use as character identity." in conditioning["inputs"]["prompt"]
    assert "2. <Audio 1> + <Video 1>: use as motion." in conditioning["inputs"]["prompt"]
    assert "3. <Audio 2>: use as voice and vocal character." in conditioning["inputs"]["prompt"]
    assert conditioning["inputs"]["prompt"].endswith("The character runs through rain and speaks clearly.")
    assert workflow.steps == 4
    assert workflow.prompt["10"]["inputs"]["lora_name"] == H3_MANIFEST.component("ref2va_turbo_lora").filename
    assert workflow.metadata and [item["asset_id"] for item in workflow.metadata["reference_map"]] == ["character", "motion", "voice"]


def test_i2v_workflow_injects_opening_and_ending_frames() -> None:
    workflow = build_h3_t2v_workflow(
        {
            "prompt": "Transition between frames",
            "mode": "i2v",
            "references": [
                _reference("ending", "image", 1, role="last_frame"),
                _reference("opening", "image", 0, role="first_frame"),
            ],
            "duration": 4,
        }
    )
    assert workflow.prompt["20"]["inputs"]["image"].endswith("opening")
    assert workflow.prompt["21"]["inputs"]["image"].endswith("ending")
    assert workflow.prompt["5"]["inputs"]["first_frame"] == ["20", 0]
    assert workflow.prompt["5"]["inputs"]["last_frame"] == ["21", 0]


def test_repository_persists_reference_roles_and_order(repository, settings: AppSettings) -> None:
    project = repository.create_project(ProjectCreate(name="Reference project"))
    source = settings.directories["inputs"] / "character.png"
    source.write_bytes(b"local-fixture")
    asset = repository.upsert_media_asset(
        {
            "id": "asset-character", "sha256": "a" * 64, "filename": source.name,
            "media_type": "image", "path": str(source), "preview_path": str(source),
            "size_bytes": source.stat().st_size, "duration": None, "width": 64, "height": 64,
            "audio_present": False, "metadata": {"fixture": True},
        },
        project["id"],
    )
    request = GenerationCreate(
        prompt="Keep this character consistent",
        project_id=project["id"],
        mode="r2v",
        references=[MediaReference(asset_id=asset["id"], media_type="image", role="character", notes="Silver markings")],
    )
    resolved = [{**asset, "asset_id": asset["id"], "role": "character", "notes": "Silver markings", "order": 0}]
    generation = repository.create_generation(request, 77, "r2v", True, resolved_references=resolved)
    assert generation["references"][0]["role"] == "character"
    assert generation["references"][0]["order"] == 0
    row = repository.db.fetchone("SELECT * FROM media_references WHERE generation_id = ?", (generation["id"],))
    assert row["asset_id"] == asset["id"]
    assert row["role"] == "character"
    assert row["notes"] == "Silver markings"
    assert next(item for item in repository.list_projects() if item["id"] == project["id"])["reference_count"] == 1


def test_media_path_validation_helpers(tmp_path: Path) -> None:
    image = tmp_path / "reference.webp"
    image.write_bytes(b"fixture")
    assert _media_type(".webp") == "image"
    assert _media_type(".mkv") == "video"
    assert _media_type(".flac") == "audio"
    assert validate_media_path(image, "image") == image.resolve()
    with pytest.raises(ValueError, match="Unsupported"):
        _media_type(".exe")
    with pytest.raises(ValueError, match="no longer exists"):
        validate_media_path(tmp_path / "missing.mp4", "video")


def _attach_test_asset(client: TestClient, settings: AppSettings) -> tuple[str, str]:
    service = client.app.state.studio
    project_id = service.repository.ensure_default_project()["id"]
    source = settings.directories["inputs"] / "api-reference.png"
    source.write_bytes(b"local-fixture")
    asset = service.repository.upsert_media_asset(
        {
            "id": "api-reference", "sha256": "b" * 64, "filename": source.name,
            "media_type": "image", "path": str(source), "preview_path": str(source),
            "size_bytes": source.stat().st_size, "duration": None, "width": 64, "height": 64,
            "audio_present": False, "metadata": {},
        },
        project_id,
    )
    return project_id, asset["id"]


def test_real_ref2va_reports_missing_models_and_mock_never_falls_back(tmp_path: Path) -> None:
    real_settings = AppSettings(data_root=tmp_path / "real", config_path=tmp_path / "real.json", mock_mode=False)
    with TestClient(create_app(real_settings)) as client:
        project_id, asset_id = _attach_test_asset(client, real_settings)
        response = client.post(
            "/api/generations",
            json={"prompt": "Reference test", "project_id": project_id, "mode": "r2v", "duration": 4,
                  "references": [{"asset_id": asset_id, "media_type": "image", "role": "character"}]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ref2va_models_missing"
        assert response.json()["detail"]["model_family"] == "ref2va"

    mock_settings = AppSettings(
        data_root=tmp_path / "mock", config_path=tmp_path / "mock.json", mock_mode=True, mock_step_delay=0.2
    )
    with TestClient(create_app(mock_settings)) as client:
        project_id, asset_id = _attach_test_asset(client, mock_settings)
        response = client.post(
            "/api/generations",
            json={"prompt": "Mock reference contract", "project_id": project_id, "mode": "r2v", "duration": 4,
                  "references": [{"asset_id": asset_id, "media_type": "image", "role": "character"}]},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["generation"]["mode"] == "r2v"
        assert payload["generation"]["is_mock"] is True
        cancelled = client.post(f"/api/jobs/{payload['job']['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
