from __future__ import annotations

import os
import random
import mimetypes
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.models.schemas import (
    GenerationAccepted,
    GenerationCreate,
    GenerationRead,
    JobRead,
    ModelInstallRequest,
    ModelVerifyRequest,
    ProjectCreate,
    ProjectRead,
    SettingsUpdate,
    UpscaleCreate,
    WorkflowCreate,
    WorkflowRead,
)
from app.config import save_machine_config
from app.providers.comfyui import ComfyUIClient
from app.services.file_safety import UnsafePathError, ensure_within_root
from app.services.system_status import get_system_status
from app.services.h3_parameters import h3_resolution
from app.services.reference_media import public_media_asset
from app.services.references import ReferenceValidationError, infer_generation_mode
from app.services.workflow_graph import InvalidWorkflowGraph, validate_graph


router = APIRouter(prefix="/api")


def studio(request: Request):
    return request.app.state.studio


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {"status": "ok", "version": settings.version, "mock_mode": settings.mock_mode}


@router.get("/system/status")
async def system_status(request: Request) -> dict[str, Any]:
    service = studio(request)
    return await get_system_status(
        request.app.state.settings,
        service.models,
        service.upscaler_models,
        service.upscalers,
    )


@router.get("/comfyui/health")
async def comfyui_health(request: Request) -> dict[str, Any]:
    return await studio(request).comfyui.health()


@router.get("/projects", response_model=list[ProjectRead])
async def projects(request: Request) -> list[dict[str, Any]]:
    return studio(request).repository.list_projects()


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, request: Request) -> dict[str, Any]:
    return studio(request).repository.create_project(payload)


@router.get("/projects/{project_id}/reference-assets")
async def project_reference_assets(project_id: str, request: Request) -> list[dict[str, Any]]:
    service = studio(request)
    if project_id not in {project["id"] for project in service.repository.list_projects()}:
        raise HTTPException(status_code=404, detail="Project not found")
    return [public_media_asset(asset) for asset in service.repository.list_project_media_assets(project_id)]


@router.post("/projects/{project_id}/reference-assets", status_code=201)
async def upload_reference_asset(
    project_id: str,
    request: Request,
    upload: UploadFile = File(...),
) -> dict[str, Any]:
    service = studio(request)
    if project_id not in {project["id"] for project in service.repository.list_projects()}:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        asset = await service.references.ingest(upload, project_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return public_media_asset(asset)


@router.get("/reference-assets/{asset_id}/{kind}")
async def reference_asset(asset_id: str, kind: str, request: Request) -> FileResponse:
    if kind not in {"content", "preview"}:
        raise HTTPException(status_code=404, detail="Reference media kind not found")
    asset = studio(request).repository.get_media_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Reference media not found")
    path_value = asset.get("preview_path") if kind == "preview" else asset.get("path")
    if not path_value:
        raise HTTPException(status_code=404, detail="Reference preview not available")
    try:
        path = ensure_within_root(Path(path_value), request.app.state.settings.data_root)
    except UnsafePathError:
        raise HTTPException(status_code=403, detail="Reference path is outside local application storage") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Reference file is missing")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=asset["filename"] if kind == "content" else None)


@router.post("/generations", response_model=GenerationAccepted, status_code=202)
async def create_generation(payload: GenerationCreate, request: Request) -> dict[str, Any]:
    service = studio(request)
    if payload.project_id is None:
        payload.project_id = service.repository.ensure_default_project()["id"]
    elif payload.project_id not in {project["id"] for project in service.repository.list_projects()}:
        raise HTTPException(status_code=400, detail="The selected project does not exist")
    try:
        references = service.references.resolve_generation_references(
            [reference.model_dump(mode="json") for reference in payload.references], payload.project_id
        )
        mode = infer_generation_mode(payload.mode.value, references)
    except (ReferenceValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not service.settings.mock_mode:
        if payload.duration < 4:
            raise HTTPException(status_code=422, detail="MiniMax H3 duration must be between 4 and 15 seconds")
        model_family = "ref2va" if mode == "r2v" else "fl2va"
        family = service.models.family_status(model_family)
        if not family["ready"]:
            missing = [
                component for component in family["components"]
                if component["status"] != "verified"
            ]
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ref2va_models_missing" if mode == "r2v" else "h3_models_missing",
                    "message": f"{family['name']} is not installed and verified. Open Models to install or repair it.",
                    "model_family": model_family,
                    "missing_bytes": sum(max(0, item["size"] - item["bytes_present"]) for item in missing),
                    "files": [item["filename"] for item in missing],
                },
            )
        width, height = h3_resolution(payload.aspect_ratio, payload.quality)
        payload.generation_resolution = f"{width}x{height}"
        payload.final_resolution = "original" if payload.upscaler == "original" else "1080p"
        if payload.upscaler != "original":
            availability = await service.upscalers.get(payload.upscaler).availability()
            if not availability.available:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "upscaler_unavailable",
                        "message": availability.reason,
                        "provider": availability.provider_id,
                        "model_family": availability.model_family,
                    },
                )
    seed = payload.seed if payload.seed is not None else random.SystemRandom().randint(0, 2**31 - 1)
    generation = service.repository.create_generation(
        payload, seed, mode, service.settings.mock_mode, resolved_references=references
    )
    job = service.repository.create_job(generation["id"], "generation")
    await service.jobs.enqueue(job["id"])
    return {"generation": generation, "job": job}


@router.get("/generations", response_model=list[GenerationRead])
async def list_generations(
    request: Request,
    search: str | None = None,
    mode: str | None = None,
    project_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    return studio(request).repository.list_generations(search=search, mode=mode, project_id=project_id, limit=limit)


@router.get("/generations/{generation_id}", response_model=GenerationRead)
async def get_generation(generation_id: str, request: Request) -> dict[str, Any]:
    generation = studio(request).repository.get_generation(generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


@router.delete("/generations/{generation_id}", status_code=204)
async def delete_generation(generation_id: str, request: Request) -> None:
    if studio(request).repository.active_upscale_job(generation_id):
        raise HTTPException(status_code=409, detail="Cancel the active upscale before deleting this generation")
    generation = studio(request).repository.delete_generation(generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")


@router.post("/generations/{generation_id}/upscale", response_model=JobRead, status_code=202)
async def upscale_generation(
    generation_id: str,
    payload: UpscaleCreate,
    request: Request,
) -> dict[str, Any]:
    service = studio(request)
    generation = service.repository.get_generation(generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    if generation["status"] not in {"completed", "upscale_failed"} or not generation["original_url"]:
        raise HTTPException(status_code=409, detail="The original video is not ready for upscaling")
    active = service.repository.active_upscale_job(generation_id)
    if active:
        raise HTTPException(status_code=409, detail={"message": "An upscale is already running", "job_id": active["id"]})
    provider = service.upscalers.get(payload.provider)
    availability = await provider.availability()
    if not availability.available:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "upscaler_unavailable",
                "message": availability.reason,
                "provider": availability.provider_id,
                "model_family": availability.model_family,
            },
        )
    job = service.repository.create_job(
        generation_id,
        "upscale",
        {"resolution": payload.resolution, "provider": payload.provider},
    )
    await service.jobs.enqueue(job["id"])
    return job


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    job = studio(request).repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    try:
        return await studio(request).jobs.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None


@router.websocket("/jobs/{job_id}/ws")
async def job_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    service = websocket.app.state.studio
    job = service.repository.get_job(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close(code=4404)
        return
    await websocket.send_json(service.jobs._public_job(job))
    queue = service.jobs.broker.subscribe(job_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
            if payload["status"] in {"completed", "failed", "upscale_failed", "cancelled"}:
                break
    except WebSocketDisconnect:
        pass
    finally:
        service.jobs.broker.unsubscribe(job_id, queue)


@router.get("/media/{generation_id}/{kind}")
async def media(generation_id: str, kind: str, request: Request) -> FileResponse:
    if kind not in {"original", "output", "thumbnail", "flashvsr", "seedvr2"}:
        raise HTTPException(status_code=404, detail="Media kind not found")
    row = studio(request).repository.db.fetchone("SELECT * FROM generations WHERE id = ?", (generation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Generation not found")
    if kind in {"flashvsr", "seedvr2"}:
        variant = studio(request).repository.db.fetchone(
            "SELECT path, status FROM generation_variants WHERE generation_id = ? AND variant = ?",
            (generation_id, kind),
        )
        path_value = variant["path"] if variant and variant["status"] == "completed" else None
    else:
        column = {"original": "original_path", "output": "output_path", "thumbnail": "thumbnail_path"}[kind]
        path_value = row[column]
    if not path_value:
        raise HTTPException(status_code=404, detail="Media file not available")
    try:
        path = ensure_within_root(Path(path_value), request.app.state.settings.data_root)
    except UnsafePathError:
        raise HTTPException(status_code=403, detail="Media path is outside local application storage") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file is missing")
    return FileResponse(path, media_type="image/jpeg" if kind == "thumbnail" else "video/mp4")


@router.post("/generations/{generation_id}/open")
async def open_generation(
    generation_id: str,
    request: Request,
    target: Annotated[str, Body(embed=True, pattern="^(file|folder)$")] = "file",
    variant: Annotated[str, Body(embed=True, pattern="^(original|flashvsr|seedvr2)$")] = "original",
) -> dict[str, bool]:
    if variant == "original":
        row = studio(request).repository.db.fetchone("SELECT original_path AS path FROM generations WHERE id = ?", (generation_id,))
    else:
        row = studio(request).repository.db.fetchone(
            "SELECT path FROM generation_variants WHERE generation_id = ? AND variant = ? AND status = 'completed'",
            (generation_id, variant),
        )
    if not row or not row["path"]:
        raise HTTPException(status_code=404, detail="Output file is not available")
    try:
        path = ensure_within_root(Path(row["path"]), request.app.state.settings.data_root)
    except UnsafePathError:
        raise HTTPException(status_code=403, detail="Output path is outside local application storage") from None
    destination = path if target == "file" else path.parent
    if not destination.exists():
        raise HTTPException(status_code=404, detail="Output path no longer exists")
    os.startfile(destination)  # type: ignore[attr-defined]  # Safe: DB path is constrained to data_root.
    return {"opened": True}


@router.get("/settings")
async def get_local_settings(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    overrides = studio(request).repository.get_settings()
    return {
        "data_root": str(settings.data_root),
        "model_path": str(settings.resolved_comfyui_path / "models"),
        "input_path": str(settings.directories["inputs"]),
        "output_path": str(settings.directories["outputs"]),
        "cache_path": str(settings.directories["cache"]),
        "comfyui_path": str(settings.comfyui_path) if settings.comfyui_path else None,
        "comfyui_host": settings.comfyui_host,
        "comfyui_port": settings.comfyui_port,
        "comfyui_mode": settings.comfyui_mode,
        "comfyui_profile": settings.comfyui_profile,
        "comfyui_auto_start": settings.comfyui_auto_start,
        "ffmpeg_path": str(settings.ffmpeg_path) if settings.ffmpeg_path else None,
        **overrides,
    }


@router.patch("/settings")
async def update_local_settings(payload: SettingsUpdate, request: Request) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    if "comfyui_host" in updates and updates["comfyui_host"] not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=400, detail="ComfyUI must use a localhost-only address")
    for key, value in updates.items():
        studio(request).repository.save_setting(key, value)
    save_machine_config(request.app.state.settings, updates)
    return {
        "saved": True,
        "restart_required": any(
            key in updates for key in {"data_root", "comfyui_host", "comfyui_port", "comfyui_path", "comfyui_mode", "comfyui_profile"}
        ),
    }


@router.get("/models")
async def list_models(request: Request) -> list[dict[str, Any]]:
    service = studio(request)
    result = service.models.all_status() + service.upscaler_models.all_status()
    for family in result:
        _store, manager = _model_services(service, family["id"])
        family["operation"] = manager.active_for(family["id"])
        if family["operation"] and family["operation"].get("current_file"):
            for component in family["components"]:
                if component["filename"] == family["operation"]["current_file"]:
                    component["status"] = "downloading" if family["operation"]["kind"] != "verify" else "verifying"
        family["target_root"] = str(service.settings.resolved_comfyui_path / "models")
    return result


@router.post("/models/install", status_code=202)
async def install_models(payload: ModelInstallRequest, request: Request) -> dict[str, Any]:
    service = studio(request)
    store, manager = _model_services(service, payload.family)
    if not payload.confirmed:
        family = store.family_status(payload.family)
        missing = [item for item in family["components"] if item["status"] != "verified"]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Explicit confirmation is required before downloading multi-gigabyte model files.",
                "total_size": family["total_size"],
                "missing_size": sum(max(0, item["size"] - item["bytes_present"]) for item in missing),
                "target_root": str(service.settings.resolved_comfyui_path / "models"),
                "files": [item["filename"] for item in missing],
            },
        )
    try:
        return manager.start_install(payload.family, repair=payload.repair)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.post("/models/verify", status_code=202)
async def verify_models(payload: ModelVerifyRequest, request: Request) -> dict[str, Any]:
    _store, manager = _model_services(studio(request), payload.family)
    try:
        return manager.start_verify(payload.family)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.get("/models/operations/{operation_id}")
async def model_operation(operation_id: str, request: Request) -> dict[str, Any]:
    service = studio(request)
    operation = service.model_downloads.get(operation_id) or service.upscaler_model_downloads.get(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="Model operation not found")
    return operation


@router.post("/models/operations/{operation_id}/cancel")
async def cancel_model_operation(operation_id: str, request: Request) -> dict[str, Any]:
    service = studio(request)
    operation = service.model_downloads.cancel(operation_id) or service.upscaler_model_downloads.cancel(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="Model operation not found")
    return operation


@router.post("/models/open")
async def open_model_folder(request: Request) -> dict[str, bool]:
    path = studio(request).settings.resolved_comfyui_path / "models"
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)  # type: ignore[attr-defined]
    return {"opened": True}


def _model_services(service: Any, family: str) -> tuple[Any, Any]:
    if family in service.models.manifest.families:
        return service.models, service.model_downloads
    if family in service.upscaler_models.manifest.families:
        return service.upscaler_models, service.upscaler_model_downloads
    raise HTTPException(status_code=404, detail=f"Unknown model family: {family}")


@router.post("/comfyui/start")
async def start_comfyui(request: Request) -> dict[str, Any]:
    if studio(request).settings.comfyui_mode != "managed":
        raise HTTPException(status_code=409, detail="External ComfyUI must be started by its owner")
    try:
        return await studio(request).runtime.start()
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.post("/comfyui/stop")
async def stop_comfyui(request: Request) -> dict[str, bool]:
    if studio(request).settings.comfyui_mode != "managed":
        raise HTTPException(status_code=409, detail="External ComfyUI is not controlled by H3 Local Studio")
    await studio(request).runtime.stop()
    return {"stopped": True}


@router.post("/comfyui/update")
async def update_comfyui(request: Request) -> dict[str, Any]:
    try:
        return await studio(request).runtime.update()
    except (RuntimeError, OSError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.get("/workflows", response_model=list[WorkflowRead])
async def workflows(request: Request) -> list[dict[str, Any]]:
    return studio(request).repository.list_workflows()


@router.post("/workflows", response_model=WorkflowRead, status_code=201)
async def create_workflow(payload: WorkflowCreate, request: Request) -> dict[str, Any]:
    try:
        validate_graph(payload.graph)
    except InvalidWorkflowGraph as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return studio(request).repository.create_workflow(payload)
