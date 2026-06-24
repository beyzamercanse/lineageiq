from __future__ import annotations

import pytest


@pytest.mark.unit
def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.unit
def test_system_status(client):
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database_reachable"] is True
    assert "customers" in body["table_counts"]
