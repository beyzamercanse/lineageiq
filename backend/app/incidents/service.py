"""Incident service: manifest generation, injection, and incident creation from alerts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.taxonomy import (
    SEVERITY_ORDER,
    IncidentType,
    RootCauseCode,
    Severity,
)
from app.detection.detectors import run_all_detectors
from app.incidents.injectors import INJECTORS, get_injector
from app.incidents.manifest import IncidentManifest
from app.incidents.restore import restore_clean_baseline
from app.models import Alert, Evidence, Incident, IncidentGroundTruth
from app.schemas.detection import AlertDTO
from app.simulator.config import GeneratorConfig

PRIMARY_SYSTEM: dict[RootCauseCode, str] = {
    RootCauseCode.DUPLICATE_TRANSACTION: "Payments",
    RootCauseCode.STALE_FX_RATE: "ForeignExchange",
    RootCauseCode.MISSING_CUSTOMER_MAPPING: "CRM",
    RootCauseCode.SCHEMA_CONTRACT_CHANGE: "Orders",
    RootCauseCode.DELAYED_PIPELINE: "Reporting",
    RootCauseCode.TIMEZONE_CONVERSION_ERROR: "Orders",
    RootCauseCode.NULL_CONTAMINATION: "Orders",
    RootCauseCode.PARTIAL_LOAD: "Orders",
    RootCauseCode.INCORRECT_AGGREGATION: "Reporting",
    RootCauseCode.UPSTREAM_API_FAILURE: "Payments",
    RootCauseCode.UNKNOWN: "Reporting",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _max_severity(alerts: list[AlertDTO]) -> Severity:
    if not alerts:
        return Severity.LOW
    return max((a.severity for a in alerts), key=SEVERITY_ORDER.index)


def _short() -> str:
    return uuid.uuid4().hex[:8]


def generate_manifests(
    session: Session, seed: int, per_type: int = 8, save: bool = True
) -> list[IncidentManifest]:
    """Plan ``per_type`` incidents for each of the ten types (default 80 total)."""
    manifests: list[IncidentManifest] = []
    for incident_type in IncidentType:
        injector = get_injector(incident_type)
        for index in range(per_type):
            manifest = injector.plan(session, seed, index)
            if save:
                manifest.save()
            manifests.append(manifest)
    return manifests


def inject_manifest(session: Session, manifest: IncidentManifest) -> list[str]:
    """Apply one incident's mutation. Records changed ids back onto the manifest."""
    injector = get_injector(manifest.incident_type)
    changed = injector.apply(session, manifest)
    manifest.changed_record_ids = changed
    manifest.injected_at = _now().isoformat()
    return changed


def persist_alerts(session: Session, alerts: list[AlertDTO]) -> list[Alert]:
    rows: list[Alert] = []
    for a in alerts:
        row = Alert(
            alert_id=f"ALRT-{_short()}",
            detector_name=a.detector_name,
            detected_at=a.detected_at,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            metric_name=a.metric_name,
            observed_value=a.observed_value,
            expected_value=a.expected_value,
            anomaly_score=a.anomaly_score,
            severity=a.severity.value,
            alert_metadata={**a.metadata, "suspected_root_cause": a.suspected_root_cause.value},
        )
        session.add(row)
        rows.append(row)
    return rows


def create_incident_from_alerts(
    session: Session,
    alerts: list[AlertDTO],
    *,
    manifest: IncidentManifest | None = None,
    incident_id: str | None = None,
    title: str | None = None,
    primary_root_cause: RootCauseCode | None = None,
) -> Incident:
    """Persist alerts, create an Incident with alert-evidence, and (if a manifest is given) the
    corresponding ground-truth row."""
    alert_rows = persist_alerts(session, alerts)
    session.flush()

    if primary_root_cause is None:
        if manifest is not None:
            primary_root_cause = manifest.root_cause_code
        else:
            named = [
                a.suspected_root_cause
                for a in alerts
                if a.suspected_root_cause != RootCauseCode.UNKNOWN
            ]
            primary_root_cause = named[0] if named else RootCauseCode.UNKNOWN

    severity = _max_severity(alerts)
    iid = incident_id or (f"INC-{manifest.manifest_id}" if manifest else f"INC-{_short()}")
    incident = Incident(
        incident_id=iid,
        title=title or (manifest.title if manifest else f"Detected: {primary_root_cause.value}"),
        detected_at=_now(),
        status="open",
        severity=severity.value,
        source_alert_id=alert_rows[0].alert_id if alert_rows else None,
        primary_affected_system=PRIMARY_SYSTEM.get(primary_root_cause, "Reporting"),
        assigned_to=None,
        created_at=_now(),
        resolved_at=None,
    )
    session.add(incident)
    session.flush()

    for a, row in zip(alerts, alert_rows):
        session.add(Evidence(
            evidence_id=f"EV-{_short()}",
            incident_id=iid,
            evidence_type="alert",
            source=a.detector_name,
            summary=(
                f"{a.detector_name}: {a.metric_name} on {a.entity_type} {a.entity_id} "
                f"observed={a.observed_value} expected={a.expected_value}"
            ),
            raw_reference=row.alert_id,
            collected_at=_now(),
            reliability_score=1.0,
            structured_payload={**a.metadata, "suspected_root_cause": a.suspected_root_cause.value},
        ))

    if manifest is not None:
        session.add(IncidentGroundTruth(
            incident_id=iid,
            injected_incident_type=manifest.incident_type.value,
            root_cause_code=manifest.root_cause_code.value,
            root_cause_description=manifest.root_cause_description,
            affected_tables=manifest.changed_tables,
            affected_jobs=[manifest.affected_pipeline] if manifest.affected_pipeline else [],
            affected_reports=manifest.expected_affected_reports,
            expected_evidence=manifest.expected_evidence,
            should_escalate=manifest.should_escalate,
            injection_manifest=manifest.model_dump(mode="json"),
            created_at=_now(),
        ))
    session.flush()
    return incident


def run_incident_pipeline(
    session: Session,
    manifest: IncidentManifest,
    *,
    config: GeneratorConfig | None = None,
    restore: bool = True,
) -> Incident:
    """Restore clean data, inject one incident, detect, and create the incident with ground truth.

    This is the per-case flow used by the demo and the evaluation runner.
    """
    if restore:
        restore_clean_baseline(session, config)
        session.flush()
    inject_manifest(session, manifest)
    session.flush()
    alerts = run_all_detectors(session)
    return create_incident_from_alerts(session, alerts, manifest=manifest)


# Re-exported for convenience / discoverability.
__all__ = [
    "INJECTORS",
    "create_incident_from_alerts",
    "generate_manifests",
    "inject_manifest",
    "persist_alerts",
    "run_incident_pipeline",
]
