"""Incident API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IncidentSummary(BaseModel):
    incident_id: str
    title: str
    detected_at: datetime
    severity: str
    status: str
    primary_affected_system: str | None
    has_investigation: bool = False
    confidence: float | None = None
    requires_human_review: bool | None = None
    leading_root_cause: str | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    evidence_type: str
    source: str
    summary: str
    collected_at: datetime
    reliability_score: float
    structured_payload: dict[str, Any] | None = None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_run_id: str
    incident_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    model_name: str
    tool_call_count: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float
    output: dict[str, Any] | None = None


class GroundTruthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    root_cause_code: str
    root_cause_description: str
    affected_tables: list[Any]
    affected_reports: list[Any]
    should_escalate: bool


class IncidentDetail(BaseModel):
    incident: IncidentSummary
    evidence: list[EvidenceOut]
    agent_runs: list[AgentRunOut]
    ground_truth: GroundTruthOut | None = None
