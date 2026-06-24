from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.agent.llm import FakeLLM
from app.agent.orchestrator import investigate_incident
from app.core.taxonomy import ALL_INCIDENT_TYPES, root_cause_for
from app.incidents.service import generate_manifests, run_incident_pipeline
from app.models import AgentRun, Base, Evidence
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset

_TOOL_EVIDENCE_TYPES = {"sql", "log", "lineage", "historical", "pipeline", "schema"}


def _seeded() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    generate_clean_dataset(s, GeneratorConfig.small())
    s.flush()
    return s


@pytest.mark.e2e
@pytest.mark.parametrize("incident_type", ALL_INCIDENT_TYPES, ids=lambda t: t.value)
def test_investigation_top1_root_cause_correct(incident_type):
    s = _seeded()
    cfg = GeneratorConfig.small()
    manifests = generate_manifests(s, seed=cfg.seed, per_type=1, save=False)
    manifest = next(m for m in manifests if m.incident_type == incident_type)
    incident = run_incident_pipeline(s, manifest, config=cfg)

    report = investigate_incident(s, incident.incident_id, llm=FakeLLM())

    assert report.root_cause_candidates, "no candidates produced"
    assert report.root_cause_candidates[0].root_cause_code == root_cause_for(incident_type).value
    s.close()


@pytest.mark.e2e
def test_stale_fx_full_demo():
    s = _seeded()
    cfg = GeneratorConfig.small()
    manifests = generate_manifests(s, seed=cfg.seed, per_type=1, save=False)
    manifest = next(m for m in manifests if m.incident_type.value == "stale_fx_rate")
    incident = run_incident_pipeline(s, manifest, config=cfg)

    report = investigate_incident(s, incident.incident_id, llm=FakeLLM())

    # Leading diagnosis is STALE_FX_RATE with cited evidence.
    top = report.root_cause_candidates[0]
    assert top.root_cause_code == "STALE_FX_RATE"
    assert top.supporting_evidence_ids
    assert report.confidence > 0.0

    # Every tool call produced a traceable Evidence row.
    tool_evidence = s.scalar(
        select(func.count()).select_from(Evidence)
        .where(Evidence.incident_id == incident.incident_id)
        .where(Evidence.evidence_type.in_(_TOOL_EVIDENCE_TYPES))
    )
    assert tool_evidence and tool_evidence >= 3

    # Lineage impact reached the revenue report / dashboards.
    assert any("revenue" in r or "dashboard" in r for r in report.impacted_reports)

    # An AgentRun was persisted with token accounting and a non-zero tool count.
    run = s.execute(select(AgentRun).where(AgentRun.incident_id == incident.incident_id)).scalar_one()
    assert run.status == "completed"
    assert run.tool_call_count >= 3
    assert run.output["root_cause_candidates"][0]["root_cause_code"] == "STALE_FX_RATE"

    # Remediation is recommended, not executed, and requires approval.
    assert report.remediation_recommendations
    assert all(r.requires_approval for r in report.remediation_recommendations)
    s.close()
