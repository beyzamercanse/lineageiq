from __future__ import annotations

import pytest


@pytest.mark.integration
def test_list_nodes(client):
    resp = client.get("/api/v1/lineage/nodes")
    assert resp.status_code == 200
    ids = {n["id"] for n in resp.json()}
    assert "fx_rates" in ids and "daily_revenue_report" in ids


@pytest.mark.integration
def test_list_nodes_filtered(client):
    resp = client.get("/api/v1/lineage/nodes", params={"node_type": "dashboard"})
    assert resp.status_code == 200
    assert all(n["type"] == "dashboard" for n in resp.json())


@pytest.mark.integration
def test_impact_endpoint(client):
    resp = client.get("/api/v1/lineage/impact", params={"node_id": "fx_rates"})
    assert resp.status_code == 200
    body = resp.json()
    assert "executive_revenue_dashboard" in body["affected_assets"]


@pytest.mark.integration
def test_path_endpoint(client):
    resp = client.get(
        "/api/v1/lineage/path",
        params={"source": "fx_api", "target": "executive_revenue_dashboard"},
    )
    assert resp.status_code == 200
    assert resp.json()["paths"][0][0] == "fx_api"


@pytest.mark.integration
def test_impact_unknown_node_404(client):
    resp = client.get("/api/v1/lineage/impact", params={"node_id": "nope"})
    assert resp.status_code == 404
