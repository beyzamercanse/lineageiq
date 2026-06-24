from __future__ import annotations

import pytest


@pytest.mark.integration
def test_run_and_list_evaluation(client):
    resp = client.post("/api/v1/evaluations/run", params={"per_type": 1, "small": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"]["n_incidents"] == 10
    assert body["metrics"]["root_cause_top1_accuracy"] == 1.0

    listing = client.get("/api/v1/evaluations")
    assert listing.status_code == 200
    assert len(listing.json()) >= 1

    run_id = body["evaluation_run_id"]
    detail = client.get(f"/api/v1/evaluations/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["evaluation_run_id"] == run_id
