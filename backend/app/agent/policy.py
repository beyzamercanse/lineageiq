"""Human-review (escalation) policy.

Escalate when any condition holds (spec §12). Kept separate from synthesis so it can be applied
and tested independently.
"""

from __future__ import annotations

from app.core.taxonomy import Severity
from app.schemas.investigation import InvestigationReport

CONFIDENCE_THRESHOLD = 0.65


def evaluate_human_review(
    report: InvestigationReport,
    *,
    distinct_evidence_sources: int,
    severity: Severity,
    budget_exhausted: bool,
    tool_conflict: bool = False,
    critical_data_unavailable: bool = False,
) -> tuple[bool, str | None]:
    """Return (requires_human_review, reason)."""
    reasons: list[str] = []

    if report.confidence < CONFIDENCE_THRESHOLD:
        reasons.append(f"confidence {report.confidence:.2f} < {CONFIDENCE_THRESHOLD}")
    if distinct_evidence_sources < 2:
        reasons.append("fewer than two independent evidence sources")
    if tool_conflict:
        reasons.append("tool results conflict")
    if budget_exhausted:
        reasons.append("investigation budget reached")
    if critical_data_unavailable:
        reasons.append("critical data unavailable")
    if severity == Severity.CRITICAL:
        reasons.append("incident severity is critical")

    candidates = report.root_cause_candidates
    if len(candidates) >= 2 and abs(candidates[0].confidence - candidates[1].confidence) < 0.1:
        reasons.append("multiple root causes similarly probable")
    if not candidates or candidates[0].root_cause_code == "UNKNOWN":
        reasons.append("root cause undetermined / outside taxonomy")

    # A remediation that could alter production data warrants approval-level review.
    if any(r.risk == "high" for r in report.remediation_recommendations):
        reasons.append("proposed remediation could alter production data")

    if reasons:
        return True, "; ".join(reasons)
    return False, None
