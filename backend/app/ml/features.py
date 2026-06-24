"""Feature extraction for ML models.

Incident-level features are derived from the deterministic detectors' alerts, so ML augments the
controls rather than replacing them. Report-level numeric features feed the Isolation Forest.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.taxonomy import SEVERITY_ORDER, Severity
from app.detection.detectors import ALL_DETECTORS
from app.models import DailyRevenueReport
from app.schemas.detection import AlertDTO

DETECTOR_NAMES: list[str] = [d.name for d in ALL_DETECTORS]

INCIDENT_FEATURE_NAMES: list[str] = [
    *[f"count_{name}" for name in DETECTOR_NAMES],
    "max_anomaly_score",
    "distinct_detectors",
    "severity_ordinal",
]


def _severity_ordinal(sev: Severity) -> int:
    return SEVERITY_ORDER.index(sev)


def extract_incident_features(alerts: list[AlertDTO]) -> list[float]:
    """Build a fixed-length numeric feature vector from an incident's alerts."""
    counts = dict.fromkeys(DETECTOR_NAMES, 0)
    max_score = 0.0
    max_sev = Severity.LOW
    for a in alerts:
        if a.detector_name in counts:
            counts[a.detector_name] += 1
        if a.anomaly_score is not None:
            max_score = max(max_score, a.anomaly_score)
        if SEVERITY_ORDER.index(a.severity) > SEVERITY_ORDER.index(max_sev):
            max_sev = a.severity
    distinct = sum(1 for c in counts.values() if c > 0)
    return [
        *[float(counts[name]) for name in DETECTOR_NAMES],
        max_score,
        float(distinct),
        float(_severity_ordinal(max_sev)),
    ]


REPORT_FEATURE_NAMES = [
    "gross_revenue", "refund_total", "net_revenue", "order_count", "payment_count",
]


def report_feature_matrix(session: Session) -> tuple[list[list[float]], list[str]]:
    """Numeric feature matrix over daily_revenue_report rows, with row keys."""
    rows: list[list[float]] = []
    keys: list[str] = []
    for r in session.execute(select(DailyRevenueReport)).scalars():
        rows.append([
            float(r.gross_revenue), float(r.refund_total), float(r.net_revenue),
            float(r.order_count), float(r.payment_count),
        ])
        keys.append(f"{r.report_date.isoformat()}:{r.region}")
    return rows, keys
