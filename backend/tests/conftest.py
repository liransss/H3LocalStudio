from pathlib import Path

import pytest

from app.config import AppSettings
from app.database import Database
from app.repositories.studio import StudioRepository


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        data_root=tmp_path / "studio",
        config_path=tmp_path / "config.json",
        mock_mode=True,
        mock_step_delay=0,
    )


@pytest.fixture
def repository(settings: AppSettings) -> StudioRepository:
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.migrate()
    return StudioRepository(database)
