from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import AppSettings, save_machine_config
from app.models.schemas import SettingsUpdate


def test_data_root_is_absolute(tmp_path: Path):
    settings = AppSettings(data_root=tmp_path / "data")
    assert settings.data_root.is_absolute()


def test_public_api_binding_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        AppSettings(data_root=tmp_path, api_host="0.0.0.0")


def test_settings_update_rejects_relative_data_root():
    with pytest.raises(ValidationError):
        SettingsUpdate(data_root="relative\\data")


def test_machine_config_is_saved_atomically(settings):
    save_machine_config(settings, {"comfyui_port": 8299, "comfyui_host": "127.0.0.1"})
    assert settings.config_path.is_file()
    assert "8299" in settings.config_path.read_text(encoding="utf-8")
