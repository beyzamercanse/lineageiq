from __future__ import annotations

import pytest

from app.agent.policy import evaluate_human_review
from app.core.taxonomy import Severity
from app.schemas.investigation import (
    InvestigationReport,
    RemediationRecommendation,
    RootCauseCandidate,
)


def _report(confidence: float, code: str = "STALE_FX_RATE", risk: str = "medium"):
    return InvestigationReport(
        incident_id="INC-x",
        summary="s",
        confidence=confidence,
        root_cause_candidates=[RootCauseCandidate(
            rank=1, root_cause_code=code, title="t", explanation="e",
            confidence=confidence, supporting_evidence_ids=["EV-1", "EV-2"],
        )],
        remediation_recommendations=[RemediationRecommendation(
            action="fix", target_system="X", risk=risk, requires_approval=True,
        )],
    )


@pytest.mark.unit
def test_confidence_out_of_range_rejected():
    with pytest.raises(ValueError):
        RootCauseCandidate(rank=1, root_cause_code="X", title="t", explanation="e", confidence=1.5)


@pytest.mark.unit
def test_low_confidence_escalates():
    requires, reason = evaluate_human_review(
        _report(0.4), distinct_evidence_sources=3, severity=Severity.MEDIUM, budget_exhausted=False,
    )
    assert requires and "confidence" in reason


@pytest.mark.unit
def test_single_evidence_source_escalates():
    requires, reason = evaluate_human_review(
        _report(0.9), distinct_evidence_sources=1, severity=Severity.MEDIUM, budget_exhausted=False,
    )
    assert requires and "independent evidence" in reason


@pytest.mark.unit
def test_high_confidence_multi_source_low_risk_no_escalation():
    requires, _ = evaluate_human_review(
        _report(0.9, risk="low"), distinct_evidence_sources=3, severity=Severity.MEDIUM,
        budget_exhausted=False,
    )
    assert requires is False


@pytest.mark.unit
def test_critical_severity_escalates():
    requires, reason = evaluate_human_review(
        _report(0.9, risk="low"), distinct_evidence_sources=3, severity=Severity.CRITICAL,
        budget_exhausted=False,
    )
    assert requires and "critical" in reason
