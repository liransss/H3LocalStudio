from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class GenerationMode(StrEnum):
    AUTO = "auto"
    T2V = "t2v"
    I2V = "i2v"
    R2V = "r2v"


class JobState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    POST_PROCESSING = "post-processing"
    UPSCALING = "upscaling"
    COMPLETED = "completed"
    FAILED = "failed"
    UPSCALE_FAILED = "upscale_failed"
    CANCELLED = "cancelled"


class MediaReference(BaseModel):
    asset_id: str
    media_type: Literal["image", "video", "audio"] | None = None
    role: Literal[
        "character", "style", "motion", "camera", "voice", "environment", "product", "general",
        "first_frame", "last_frame"
    ] = "general"
    notes: str = Field(default="", max_length=500)


class GenerationCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    project_id: str | None = None
    mode: GenerationMode = GenerationMode.AUTO
    references: list[MediaReference] = Field(default_factory=list, max_length=12)
    duration: int = Field(default=5, ge=1, le=15)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"] = "16:9"
    generation_resolution: str = "1344x768"
    final_resolution: Literal["original", "1080p", "1440p", "4k"] = "1080p"
    upscaler: Literal["original", "flashvsr", "seedvr2"] = "original"
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    steps: int = Field(default=20, ge=1, le=100)
    turbo: bool = False
    profile: Literal["balanced", "quality"] = "balanced"
    quality: Literal["preview", "high"] = "high"
    fps: int = Field(default=24, ge=8, le=60)
    audio_enabled: bool = True

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Prompt cannot be blank")
        return clean


class GenerationRead(BaseModel):
    id: str
    project_id: str | None
    prompt: str
    mode: str
    seed: int
    status: str
    progress: float
    stage: str
    parameters: dict[str, Any]
    references: list[dict[str, Any]]
    original_url: str | None = None
    output_url: str | None = None
    thumbnail_url: str | None = None
    variants: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    error_details: str | None = None
    output_metadata: dict[str, Any] = Field(default_factory=dict)
    comfy_prompt_id: str | None = None
    execution_seconds: float | None = None
    model_manifest_version: str | None = None
    is_mock: bool
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class JobRead(BaseModel):
    id: str
    generation_id: str | None
    kind: str
    status: str
    progress: float
    stage: str
    error_message: str | None = None
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class GenerationAccepted(BaseModel):
    generation: GenerationRead
    job: JobRead


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectRead(ProjectCreate):
    id: str
    reference_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkflowNode(BaseModel):
    id: str
    type: str
    position: dict[str, float]
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    version: int = 1


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    graph: WorkflowGraph


class WorkflowRead(WorkflowCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class SettingsUpdate(BaseModel):
    data_root: str | None = None
    comfyui_path: str | None = None
    comfyui_host: str | None = None
    comfyui_port: int | None = Field(default=None, ge=1, le=65535)
    comfyui_mode: Literal["managed", "external"] | None = None
    comfyui_profile: Literal["balanced", "low_vram"] | None = None
    comfyui_auto_start: bool | None = None
    ffmpeg_path: str | None = None
    default_profile: Literal["balanced", "quality"] | None = None
    default_final_resolution: Literal["original", "1080p", "1440p", "4k"] | None = None
    default_upscaler: Literal["original", "flashvsr", "seedvr2"] | None = None

    @field_validator("data_root")
    @classmethod
    def absolute_data_root(cls, value: str | None) -> str | None:
        if value is not None and not Path(value).is_absolute():
            raise ValueError("Application data root must be an absolute Windows path")
        return value


class ModelInstallRequest(BaseModel):
    family: Literal["fl2va", "ref2va", "flashvsr", "seedvr2"] = "fl2va"
    confirmed: bool = False
    repair: bool = False


class ModelVerifyRequest(BaseModel):
    family: Literal["fl2va", "ref2va", "flashvsr", "seedvr2"] = "fl2va"


class UpscaleCreate(BaseModel):
    provider: Literal["flashvsr", "seedvr2"]
    resolution: Literal["1080p"] = "1080p"
