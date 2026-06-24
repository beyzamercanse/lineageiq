from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.validation import validate_report
from app.models import Base, Evidence, Incident
from app.schemas.investigation import (
    InvestigationReport,
    RemediationRecommendation,
    RootCauseCandidate,
)


def _session_with_incident() -> tuple[Session, list[str]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    now = datetime.now(timezone.utc)
    s.add(Incident(incident_id="INC-1", title="t", detected_at=now, status="open",
                   severity="high", created_at=now))
    ids = []
    for i, etype in enumerate(["sql", "lineage"]):
        eid = f"EV-{i}"
        s.add(Evidence(evidence_id=eid, incident_id="INC-1", evidence_type=etype,
                       source="x", summary="s", collected_at=now, reliability_score=1.0))
        ids.append(eid)
    s.flush()
    return s, ids


def _report(**kwargs) -> InvestigationReport:
    defaults = {
        "incident_id": "INC-1", "summary": "s", "confidence": 0.8,
        "remediation_recommendations": [RemediationRecommendation(
            action="Refresh FX data", target_system="FX", risk="medium", requires_approval=True)],
    }
    defaults.update(kwargs)
    return InvestigationReport(**defaults)


@pytest.mark.unit
def test_valid_report_passes():
    s, ids = _session_with_incident()
    report = _report(evidence_ids=ids, root_cause_candidates=[RootCauseCandidate(
        rank=1, root_cause_code="STALE_FX_RATE", title="t", explanation="e",
        confidence=0.8, supporting_evidence_ids=ids)])
    result = validate_report(s, report)
    assert result.passed, result.issues
    s.close()


@pytest.mark.unit
def test_invalid_evidence_id_flagged():
    s, ids = _session_with_incident()
    report = _report(evidence_ids=["EV-DOES-NOT-EXIST"], root_cause_candidates=[RootCauseCandidate(
        rank=1, root_cause_code="STALE_FX_RATE", title="t", explanation="e",
        confidence=0.8, supporting_evidence_ids=["EV-DOES-NOT-EXIST"])])
    result = validate_report(s, report)
    assert not result.passed
    assert any(i.code == "invalid_evidence_id" for i in result.issues)
    s.close()


@pytest.mark.unit
def test_unsupported_high_confidence_flagged():
    s, _ids = _session_with_incident()
    report = _report(root_cause_candidates=[RootCauseCandidate(
        rank=1, root_cause_code="STALE_FX_RATE", title="t", explanation="e",
        confidence=0.9, supporting_evidence_ids=[])])
    result = validate_report(s, report)
    assert not result.passed
    assert result.unsupported_claims
    assert any(i.code == "unsupported_high_confidence" for i in result.issues)
    s.close()


@pytest.mark.unit
def test_remediation_claimed_executed_flagged():
    s, ids = _session_with_incident()
    report = _report(
        evidence_ids=ids,
        root_cause_candidates=[RootCauseCandidate(
            rank=1, root_cause_code="STALE_FX_RATE", title="t", explanation="e",
            confidence=0.8, supporting_evidence_ids=ids)],
        remediation_recommendations=[RemediationRecommendation(
            action="FX data has been fixed and applied", target_system="FX",
            risk="medium", requires_approval=True)],
    )
    result = validate_report(s, report)
    assert not result.passed
    assert any(i.code == "remediation_claimed_executed" for i in result.issues)
    s.close()
