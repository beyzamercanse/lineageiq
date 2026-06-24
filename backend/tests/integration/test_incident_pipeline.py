from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import ALL_INCIDENT_TYPES, root_cause_for
from app.incidents.service import generate_manifests, run_incident_pipeline
from app.models import Base, Incident, IncidentGroundTruth, Order
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset


def _seeded() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    generate_clean_dataset(s, GeneratorConfig.small())
    s.flush()
    return s


@pytest.mark.integration
def test_generate_manifests_creates_80(tmp_path, monkeypatch):
    import app.incidents.manifest as manifest_mod

    monkeypatch.setattr(manifest_mod, "MANIFEST_DIR", tmp_path)
    s = _seeded()
    manifests = generate_manifests(s, seed=GeneratorConfig.small().seed, per_type=8, save=True)
    assert len(manifests) == 80
    assert len(list(tmp_path.glob("*.json"))) == 80
    s.close()


@pytest.mark.integration
@pytest.mark.parametrize("incident_type", ALL_INCIDENT_TYPES, ids=lambda t: t.value)
def test_pipeline_creates_incident_with_correct_ground_truth(incident_type):
    s = _seeded()
    cfg = GeneratorConfig.small()
    manifest = generate_manifests(s, seed=cfg.seed, per_type=1, save=False)
    manifest = next(m for m in manifest if m.incident_type == incident_type)

    incident = run_incident_pipeline(s, manifest, config=cfg)
    assert isinstance(incident, Incident)

    gt = s.get(IncidentGroundTruth, incident.incident_id)
    assert gt is not None
    assert gt.root_cause_code == root_cause_for(incident_type).value
    s.close()


@pytest.mark.integration
def test_restore_between_cases_isolates_incidents():
    s = _seeded()
    cfg = GeneratorConfig.small()
    manifests = generate_manifests(s, seed=cfg.seed, per_type=1, save=False)

    # Run two different incidents in sequence; each restores clean first.
    dup = next(m for m in manifests if m.incident_type.value == "duplicate_transaction")
    stale = next(m for m in manifests if m.incident_type.value == "stale_fx_rate")

    run_incident_pipeline(s, dup, config=cfg)
    orders_after_first = s.scalar(select(func.count()).select_from(Order))
    run_incident_pipeline(s, stale, config=cfg)  # restores clean, so only stale-fx remains
    orders_after_second = s.scalar(select(func.count()).select_from(Order))

    # restore regenerates the same clean order set each time.
    assert orders_after_first == orders_after_second == cfg.n_orders
    s.close()
