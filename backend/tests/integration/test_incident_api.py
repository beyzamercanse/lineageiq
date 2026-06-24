from __future__ import annotations

import pytest

from app.db.session import session_scope
from app.incidents.service import generate_manifests, run_incident_pipeline
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset


@pytest.fixture
def stale_fx_incident():
    cfg = GeneratorConfig.small()
    with session_scope() as session:
        generate_clean_dataset(session, cfg)
        manifests = generate_manifests(session, seed=cfg.seed, per_type=1, save=False)
        manifest = next(m for m in manifests if m.incident_type.value == "stale_fx_rate")
        incident = run_incident_pipeline(session, manifest, config=cfg)
        return incident.incident_id


@pytest.mark.integration
def test_list_and_detail(client, stale_fx_incident):
    resp = client.get("/api/v1/incidents")
    assert resp.status_code == 200
    ids = {i["incident_id"] for i in resp.json()}
    assert stale_fx_incident in ids

    detail = client.get(f"/api/v1/incidents/{stale_fx_incident}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["incident"]["incident_id"] == stale_fx_incident
    assert body["ground_truth"]["root_cause_code"] == "STALE_FX_RATE"


@pytest.mark.integration
def test_investigate_endpoint(client, stale_fx_incident):
    resp = client.post(f"/api/v1/incidents/{stale_fx_incident}/investigate")
    assert resp.status_code == 200
    report = resp.json()
    assert report["root_cause_candidates"][0]["root_cause_code"] == "STALE_FX_RATE"

    runs = client.get(f"/api/v1/incidents/{stale_fx_incident}/agent-runs")
    assert runs.status_code == 200
    assert len(runs.json()) >= 1


@pytest.mark.integration
def test_detail_404(client):
    assert client.get("/api/v1/incidents/NOPE").status_code == 404
