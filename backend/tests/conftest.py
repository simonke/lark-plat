"""Shared fixtures for lark-plat backend unit tests.

Contract v2.1 baseline (api-design v2.1):
  - Result envelope {code,message,data}; error codes 0/400/401/403/404/409/422/429/500/1001
  - snake_case JSON fields
  - pagination data -> {list,total,page,size}
  - settings override for tests (in-memory / isolated Redis prefix)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "docs" / "openapi.json"


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test-environment settings override (no .env / no external DB)."""
    return Settings(
        app_env="test",
        debug=False,
        database_url="postgresql+psycopg2://lark:lark@localhost:5432/lark_plat",
        redis_url="redis://localhost:6379/15",
        celery_broker_url="redis://localhost:6379/15",
        celery_result_backend="redis://localhost:6379/15",
        audit_append_only=True,
    )


@pytest.fixture(scope="session")
def openapi_spec() -> dict:
    """Loaded /openapi.json contract artifact for static assertions."""
    with OPENAPI_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)
