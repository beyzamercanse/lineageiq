"""Integration: the real seed -> validate path through config + session layer.

Runs against the conftest temp database (SQLite by default; Postgres in CI when DATABASE_URL is a
Postgres URL).
"""

from __future__ import annotations

import pytest

from app.db.cli import create_all
from app.db.session import session_scope
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset
from app.simulator.validator import validate_clean_baseline


@pytest.mark.integration
def test_seed_then_validate_passes():
    create_all()
    with session_scope() as session:
        counts = generate_clean_dataset(session, GeneratorConfig.small())
    assert counts["orders"] == 600

    with session_scope() as session:
        report = validate_clean_baseline(session)
    failed = [(c.name, c.detail) for c in report.checks if not c.passed]
    assert report.passed, f"failed: {failed}"


@pytest.mark.integration
def test_status_endpoint_reflects_seeded_data(client):
    create_all()
    with session_scope() as session:
        generate_clean_dataset(session, GeneratorConfig.small())
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    counts = resp.json()["table_counts"]
    assert counts["customers"] == 40
    assert counts["orders"] == 600
