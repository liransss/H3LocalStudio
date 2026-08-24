from __future__ import annotations

import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_root() -> Path:
    preferred_drive = Path("F:/")
    if preferred_drive.exists():
        return preferred_drive / "AI" / "H3LocalStudio"
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "H3LocalStudio"


def default_config_path() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "H3LocalStudio" / "config.json"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="H3_",
        env_file=("backend/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "H3 Local Studio"
    version: str = "0.1.0"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=7331, ge=1024, le=65535)
    config_path: Path = Field(default_factory=default_config_path)
    data_root: Path = Field(default_factory=default_data_root)
    mock_mode: bool = False
    mock_step_delay: float = Field(default=0.45, ge=0, le=10)
    mock_failure: bool = False
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = Field(default=8188, ge=1, le=65535)
    comfyui_path: Path | None = None
    comfyui_mode: Literal["managed", "external"] = "managed"
    comfyui_profile: Literal["balanced", "low_vram"] = "balanced"
    comfyui_auto_start: bool = False
    ffmpeg_path: Path | None = None
    max_gpu_jobs: int = Field(default=1, ge=1, le=4)

    @field_validator("api_host", "comfyui_host")
    @classmethod
    def localhost_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("H3 Local Studio services must bind to localhost")
        return value

    @field_validator("data_root")
    @classmethod
    def normalize_data_root(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def database_path(self) -> Path:
        return self.data_root / "database" / "studio.db"

    @property
    def comfyui_url(self) -> str:
        return f"http://{self.comfyui_host}:{self.comfyui_port}"

    @property
    def resolved_comfyui_path(self) -> Path:
        return (self.comfyui_path or (self.data_root / "runtime" / "ComfyUI")).expanduser().resolve()

    @property
    def directories(self) -> dict[str, Path]:
        return {
            name: self.data_root / name
            for name in (
                "models",
                "inputs",
                "outputs",
                "projects",
                "cache",
                "workflows",
                "thumbnails",
                "temp",
                "logs",
                "database",
                "runtime",
            )
        }

    def ensure_directories(self) -> None:
        for directory in self.directories.values():
            directory.mkdir(parents=True, exist_ok=True)


def save_machine_config(settings: AppSettings, updates: dict[str, object]) -> None:
    allowed = {
        "data_root",
        "comfyui_path",
        "comfyui_host",
        "comfyui_port",
        "comfyui_mode",
        "comfyui_profile",
        "comfyui_auto_start",
        "ffmpeg_path",
        "default_profile",
        "default_final_resolution",
        "default_upscaler",
    }
    path = settings.config_path
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update({key: value for key, value in updates.items() if key in allowed})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    temporary.replace(path)


@lru_cache
def get_settings() -> AppSettings:
    environment_settings = AppSettings()
    path = environment_settings.config_path
    if not path.is_file():
        return environment_settings
    try:
        local_values = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return environment_settings
    merged = environment_settings.model_dump()
    for key, value in local_values.items():
        environment_name = f"H3_{key.upper()}"
        if key in AppSettings.model_fields and environment_name not in os.environ:
            merged[key] = value
    return AppSettings(**merged)
