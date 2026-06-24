"""Deterministic severity scoring.

Severity is a function of business impact features (affected records, monetary exposure, number of
downstream reports) plus an incident-type base weight for categories that are inherently
operationally or financially sensitive. Documented here per docs/EVALUATION.md.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.taxonomy import IncidentType, Severity

# Incident types that carry an extra financial/operational sensitivity weight.
_BASE_WEIGHT: dict[IncidentType, int] = {
    IncidentType.STALE_FX_RATE: 1,
    IncidentType.SCHEMA_CHANGE: 1,
    IncidentType.INCORRECT_AGGREGATION: 1,
    IncidentType.UPSTREAM_API_FAILURE: 1,
    IncidentType.TIMEZONE_CONVERSION_ERROR: 1,
    IncidentType.PARTIAL_LOAD: 1,
}


def compute_severity(
    *,
    affected_records: int,
    monetary_exposure: Decimal,
    downstream_reports: int,
    incident_type: IncidentType,
) -> Severity:
    """Map impact features to a Severity level."""
    score = 0

    if monetary_exposure >= Decimal("100000"):
        score += 2
    elif monetary_exposure >= Decimal("25000"):
        score += 1

    if affected_records >= 100:
        score += 2
    elif affected_records >= 10:
        score += 1

    if downstream_reports >= 2:
        score += 1

    score += _BASE_WEIGHT.get(incident_type, 0)

    if score >= 5:
        return Severity.CRITICAL
    if score >= 3:
        return Severity.HIGH
    if score == 2:
        return Severity.MEDIUM
    return Severity.LOW
