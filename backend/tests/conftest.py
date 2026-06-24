"""Shared pytest fixtures. Uses a temp SQLite DB so tests need no Postgres."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Configure environment BEFORE importing app modules that read settings.
_TMP_DIR = tempfile.mkdtemp(prefix="lineageiq_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("RANDOM_SEED", "20240601")


@pytest.fixture(scope="session", autouse=True)
def _setup_database() -> Iterator[None]:
    from app.core.config import get_settings
    from app.db.cli import reset
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()
    reset()
    yield


@pytest.fixture
def db_session() -> Iterator:
    from app.db.session import get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator:
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
