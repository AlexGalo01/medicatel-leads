from __future__ import annotations

import os

# Debe ejecutarse antes de importar modulos que llaman a get_settings() en import-time (p. ej. db.base).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("EXA_API_KEY", "x")
os.environ.setdefault("GOOGLE_API_KEY", "x")

import pytest

from mle.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
