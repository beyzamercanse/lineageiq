"""Evidence-grounding and hallucination validation (deterministic).

Runs after the agent produces its report. Does not rely on an LLM to validate an LLM. Checks that
every cited evidence id exists and belongs to the incident, that confidence is consistent with
evidence coverage, that root-cause codes are in the taxonomy, that no remediation is claimed as
already executed, and flags unsupported claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.taxonomy import RootCauseCode
from app.models import Evidence
from app.schemas.investigation import InvestigationReport

_EXECUTED_WORDS = (
    "executed", "applied", "performed", "completed the", "has been fixed", "resolved",
)
_VALID_CODES = {c.value for c in RootCauseCode}
_CONFIDENCE_THRESHOLD = 0.65


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    passed: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)

    def add(self, code: str, message: str, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(code=code, message=message, severity=severity))
        if severity == "error":
            self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [{"code": i.code, "message": i.message, "severity": i.severity}
                       for i in self.issues],
            "unsupported_claims": self.unsupported_claims,
        }


def validate_report(session: Session, report: InvestigationReport) -> ValidationResult:
    """Validate a report against persisted evidence for its incident."""
    result = ValidationResult()

    evidence_rows = {
        e.evidence_id: e for e in session.execute(
            select(Evidence).where(Evidence.incident_id == report.incident_id)
        ).scalars()
    }
    valid_ids = set(evidence_rows)

    # 1. Cited evidence ids must exist and belong to this incident.
    cited = set(report.evidence_ids)
    for c in report.root_cause_candidates:
        cited.update(c.supporting_evidence_ids)
        cited.update(c.contradictory_evidence_ids)
    invalid = sorted(e for e in cited if e and e not in valid_ids)
    if invalid:
        result.add("invalid_evidence_id",
                   f"Report cites evidence not belonging to the incident: {invalid}")

    # 2. Root-cause codes must be in the taxonomy.
    for c in report.root_cause_candidates:
        if c.root_cause_code not in _VALID_CODES:
            result.add("unknown_root_cause_code",
                       f"Root-cause code not in taxonomy: {c.root_cause_code}")

    # 3. Unsupported claims: candidates without supporting evidence.
    for c in report.root_cause_candidates:
        valid_support = [e for e in c.supporting_evidence_ids if e in valid_ids]
        if not valid_support:
            result.unsupported_claims.append(
                f"Candidate '{c.root_cause_code}' has no valid supporting evidence"
            )
            if c.confidence >= _CONFIDENCE_THRESHOLD:
                result.add(
                    "unsupported_high_confidence",
                    f"Candidate '{c.root_cause_code}' has high confidence "
                    f"({c.confidence:.2f}) with no supporting evidence",
                )

    # 4. Confidence consistent with evidence coverage (>=2 independent sources for high conf).
    if report.root_cause_candidates:
        leading = report.root_cause_candidates[0]
        distinct_sources = {
            evidence_rows[e].evidence_type
            for e in leading.supporting_evidence_ids if e in evidence_rows
        }
        if leading.confidence >= _CONFIDENCE_THRESHOLD and len(distinct_sources) < 2:
            result.add(
                "confidence_exceeds_evidence",
                f"Leading confidence {leading.confidence:.2f} but only "
                f"{len(distinct_sources)} independent evidence source(s)",
                severity="warning",
            )

    # 5. No remediation may be claimed as already executed.
    for r in report.remediation_recommendations:
        text = r.action.lower()
        if any(w in text for w in _EXECUTED_WORDS) or not r.requires_approval:
            result.add(
                "remediation_claimed_executed",
                f"Remediation must require approval and not claim execution: '{r.action}'",
            )

    return result
