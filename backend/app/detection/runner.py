"""Detection runner: run controls, persist alerts, and create incidents grouped by root cause.

Used by ``make detect`` for ad-hoc detection (no manifest/ground truth). The evaluation/demo flow
uses ``incidents.service.run_incident_pipeline`` instead, which attaches ground truth.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.taxonomy import RootCauseCode
from app.detection.detectors import run_all_detectors
from app.incidents.service import create_incident_from_alerts
from app.models import Incident
from app.schemas.detection import AlertDTO


def run_detection(session: Session) -> list[AlertDTO]:
    """Run all deterministic controls and return alerts (no persistence)."""
    return run_all_detectors(session)


def run_and_create_incidents(session: Session) -> list[Incident]:
    """Run controls, then create one incident per distinct suspected root cause.

    Generic reconciliation alerts (UNKNOWN) are attached to the most relevant root-cause incident
    when one exists; otherwise they form their own incident.
    """
    alerts = run_all_detectors(session)
    by_cause: dict[RootCauseCode, list[AlertDTO]] = defaultdict(list)
    for a in alerts:
        by_cause[a.suspected_root_cause].append(a)

    named_causes = [c for c in by_cause if c != RootCauseCode.UNKNOWN]
    # Fold generic reconciliation alerts into a single named incident if exactly one exists.
    if len(named_causes) == 1 and RootCauseCode.UNKNOWN in by_cause:
        by_cause[named_causes[0]].extend(by_cause.pop(RootCauseCode.UNKNOWN))

    incidents: list[Incident] = []
    for cause, cause_alerts in by_cause.items():
        incident = create_incident_from_alerts(
            session, cause_alerts, primary_root_cause=cause
        )
        incidents.append(incident)
    return incidents
