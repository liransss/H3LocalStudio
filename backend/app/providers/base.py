from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ProgressCallback = Callable[[float, str], Awaitable[None]]


@dataclass(frozen=True)
class GenerationArtifact:
    path: Path
    provider_job_id: str | None = None
    workflow_family: str = "unknown"
    model_files: tuple[str, ...] = ()
    manifest_version: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpscalerAvailability:
    provider_id: str
    display_name: str
    available: bool
    models_ready: bool
    runtime_ready: bool
    reason: str | None = None
    model_family: str | None = None


@dataclass(frozen=True)
class UpscaleArtifact:
    path: Path
    provider_id: str
    display_name: str
    model_files: tuple[str, ...] = ()
    manifest_version: str | None = None
    provider_job_id: str | None = None
    metadata: dict[str, Any] | None = None


class VideoGenerationProvider(ABC):
    @abstractmethod
    async def generate(
        self, generation_id: str, parameters: dict[str, Any], output_dir: Path, progress: ProgressCallback
    ) -> GenerationArtifact:
        raise NotImplementedError

    async def cancel(self) -> None:
        return None


class VideoUpscalerProvider(ABC):
    provider_id: str
    display_name: str
    model_family: str | None = None

    @abstractmethod
    async def availability(self) -> UpscalerAvailability:
        raise NotImplementedError

    @abstractmethod
    def required_models(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    async def install(self, *, confirmed: bool, repair: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def validate(self) -> UpscalerAvailability:
        raise NotImplementedError

    @abstractmethod
    async def upscale(
        self,
        source: Path,
        destination: Path,
        resolution: str,
        progress: ProgressCallback,
        aspect_ratio: str = "16:9",
        seed: int = 0,
    ) -> UpscaleArtifact:
        raise NotImplementedError

    async def cancel(self) -> None:
        return None


class FrameInterpolationProvider(ABC):
    @abstractmethod
    async def interpolate(self, source: Path, destination: Path, fps: int, progress: ProgressCallback) -> Path:
        raise NotImplementedError
