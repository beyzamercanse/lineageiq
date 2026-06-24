"""Incident API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import investigate_incident
from app.core.errors import NotFoundError
from app.db.session import get_db, session_scope
from app.models import Incident
from app.schemas.incident import AgentRunOut, EvidenceOut, IncidentDetail, IncidentSummary
from app.schemas.investigation import InvestigationReport
from app.services.incident_query import (
    get_incident_agent_runs,
    get_incident_detail,
    get_incident_evidence,
    list_incidents,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentSummary])
def list_all(db: Session = Depends(get_db)) -> list[IncidentSummary]:
    return list_incidents(db)


@router.get("/{incident_id}", response_model=IncidentDetail)
def detail(incident_id: str, db: Session = Depends(get_db)) -> IncidentDetail:
    result = get_incident_detail(db, incident_id)
    if result is None:
        raise NotFoundError(f"Incident not found: {incident_id}")
    return result


@router.get("/{incident_id}/evidence", response_model=list[EvidenceOut])
def evidence(incident_id: str, db: Session = Depends(get_db)) -> list[EvidenceOut]:
    return get_incident_evidence(db, incident_id)


@router.get("/{incident_id}/agent-runs", response_model=list[AgentRunOut])
def agent_runs(incident_id: str, db: Session = Depends(get_db)) -> list[AgentRunOut]:
    return get_incident_agent_runs(db, incident_id)


@router.post("/{incident_id}/investigate", response_model=InvestigationReport)
def investigate(incident_id: str) -> InvestigationReport:
    with session_scope() as session:
        if session.get(Incident, incident_id) is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        return investigate_incident(session, incident_id)
