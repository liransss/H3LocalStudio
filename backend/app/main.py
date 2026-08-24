from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import AppSettings, get_settings
from app.database import Database
from app.jobs.manager import JobManager
from app.providers.comfyui import ComfyUIClient, MiniMaxH3Provider
from app.providers.ffmpeg import FFmpegUpscaler, find_ffmpeg
from app.providers.mock import MockVideoProvider
from app.providers.upscalers import ComfyAIUpscaler, VideoUpscalerRegistry
from app.repositories.studio import StudioRepository
from app.services.comfyui_runtime import ComfyUIRuntime
from app.services.model_downloads import ModelDownloadManager
from app.services.model_store import H3ModelStore
from app.services.reference_media import ReferenceMediaService
from app.services.upscaler_model_store import UpscalerModelStore


@dataclass
class StudioServices:
    settings: AppSettings
    repository: StudioRepository
    jobs: JobManager
    comfyui: ComfyUIClient
    runtime: ComfyUIRuntime
    models: H3ModelStore
    model_downloads: ModelDownloadManager
    upscaler_models: UpscalerModelStore
    upscaler_model_downloads: ModelDownloadManager
    upscalers: VideoUpscalerRegistry
    references: ReferenceMediaService


def configure_logging(settings: AppSettings) -> None:
    log_file = settings.directories["logs"] / "backend.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


def create_app(settings: AppSettings | None = None) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_settings.ensure_directories()
        configure_logging(active_settings)
        database = Database(active_settings.database_path)
        database.migrate()
        repository = StudioRepository(database)
        repository.ensure_default_project()
        ffmpeg = find_ffmpeg(active_settings.ffmpeg_path)
        comfyui = ComfyUIClient(active_settings.comfyui_url)
        runtime = ComfyUIRuntime(active_settings, comfyui)
        models = H3ModelStore(active_settings.resolved_comfyui_path, active_settings.directories["cache"])
        model_downloads = ModelDownloadManager(models)
        upscaler_models = UpscalerModelStore(
            active_settings.resolved_comfyui_path,
            active_settings.directories["cache"],
            managed_runtime=active_settings.comfyui_mode == "managed",
        )
        upscaler_model_downloads = ModelDownloadManager(
            upscaler_models,
            prepare_install=upscaler_models.prepare_family,
        )
        provider = (
            MockVideoProvider(ffmpeg, active_settings.mock_step_delay, active_settings.mock_failure)
            if active_settings.mock_mode
            else MiniMaxH3Provider(comfyui, models, runtime)
        )
        upscalers = VideoUpscalerRegistry(
            [
                ComfyAIUpscaler(
                    "flashvsr", "FlashVSR · Fast 1080p", comfyui, runtime,
                    upscaler_models, upscaler_model_downloads, ffmpeg,
                ),
                ComfyAIUpscaler(
                    "seedvr2", "SeedVR2 · Best Quality 1080p", comfyui, runtime,
                    upscaler_models, upscaler_model_downloads, ffmpeg,
                ),
            ]
        )
        references = ReferenceMediaService(active_settings.data_root, repository, ffmpeg)
        jobs = JobManager(
            active_settings,
            repository,
            provider,
            upscalers,
            FFmpegUpscaler(ffmpeg),
            ffmpeg,
        )
        app.state.settings = active_settings
        app.state.studio = StudioServices(
            active_settings,
            repository,
            jobs,
            comfyui,
            runtime,
            models,
            model_downloads,
            upscaler_models,
            upscaler_model_downloads,
            upscalers,
            references,
        )
        await jobs.start()
        if active_settings.comfyui_auto_start and active_settings.comfyui_mode == "managed" and not active_settings.mock_mode:
            try:
                await runtime.start()
            except RuntimeError as error:
                logging.getLogger(__name__).warning("Managed ComfyUI auto-start failed: %s", error)
        yield
        await jobs.stop()
        await model_downloads.stop()
        await upscaler_model_downloads.stop()
        await runtime.stop()

    app = FastAPI(
        title="H3 Local Studio API",
        version=active_settings.version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()
