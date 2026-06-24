"""Read services for incident listing/detail (business logic outside route handlers)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, Evidence, Incident, IncidentGroundTruth
from app.schemas.incident import (
    AgentRunOut,
    EvidenceOut,
    GroundTruthOut,
    IncidentDetail,
    IncidentSummary,
)


def _latest_run(session: Session, incident_id: str) -> AgentRun | None:
    return session.execute(
        select(AgentRun).where(AgentRun.incident_id == incident_id)
        .order_by(AgentRun.started_at.desc())
    ).scalars().first()


def _summary(session: Session, incident: Incident) -> IncidentSummary:
    run = _latest_run(session, incident.incident_id)
    confidence = None
    requires_human = None
    leading = None
    if run is not None and run.output:
        confidence = run.output.get("confidence")
        requires_human = run.output.get("requires_human_review")
        candidates = run.output.get("root_cause_candidates") or []
        if candidates:
            leading = candidates[0].get("root_cause_code")
    return IncidentSummary(
        incident_id=incident.incident_id,
        title=incident.title,
        detected_at=incident.detected_at,
        severity=incident.severity,
        status=incident.status,
        primary_affected_system=incident.primary_affected_system,
        has_investigation=run is not None,
        confidence=confidence,
        requires_human_review=requires_human,
        leading_root_cause=leading,
    )


def list_incidents(session: Session) -> list[IncidentSummary]:
    incidents = session.execute(
        select(Incident).order_by(Incident.detected_at.desc())
    ).scalars().all()
    return [_summary(session, i) for i in incidents]


def get_incident_detail(session: Session, incident_id: str) -> IncidentDetail | None:
    incident = session.get(Incident, incident_id)
    if incident is None:
        return None
    evidence = session.execute(
        select(Evidence).where(Evidence.incident_id == incident_id)
        .order_by(Evidence.collected_at)
    ).scalars().all()
    runs = session.execute(
        select(AgentRun).where(AgentRun.incident_id == incident_id)
        .order_by(AgentRun.started_at.desc())
    ).scalars().all()
    gt = session.get(IncidentGroundTruth, incident_id)
    return IncidentDetail(
        incident=_summary(session, incident),
        evidence=[EvidenceOut.model_validate(e) for e in evidence],
        agent_runs=[AgentRunOut.model_validate(r) for r in runs],
        ground_truth=GroundTruthOut.model_validate(gt) if gt is not None else None,
    )


def get_incident_evidence(session: Session, incident_id: str) -> list[EvidenceOut]:
    rows = session.execute(
        select(Evidence).where(Evidence.incident_id == incident_id)
        .order_by(Evidence.collected_at)
    ).scalars().all()
    return [EvidenceOut.model_validate(e) for e in rows]


def get_incident_agent_runs(session: Session, incident_id: str) -> list[AgentRunOut]:
    rows = session.execute(
        select(AgentRun).where(AgentRun.incident_id == incident_id)
        .order_by(AgentRun.started_at.desc())
    ).scalars().all()
    return [AgentRunOut.model_validate(r) for r in rows]
