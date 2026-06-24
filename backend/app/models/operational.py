"""Operational ORM models: pipelines, logs, incidents, alerts, evidence, agent runs,
ground truth, historical incidents, evaluation runs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PipelineDefinition(Base):
    __tablename__ = "pipeline_definitions"

    pipeline_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(80), unique=True)
    source_system: Mapped[str] = mapped_column(String(40))
    target_system: Mapped[str] = mapped_column(String(40))
    schedule: Mapped[str] = mapped_column(String(40))
    owner: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(default=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    pipeline_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipeline_definitions.pipeline_id"))
    started_at: Mapped[datetime] = mapped_column(index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", nullable=True)


class SystemLog(Base):
    __tablename__ = "system_logs"

    log_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(index=True)
    service: Mapped[str] = mapped_column(String(60), index=True)
    log_level: Mapped[str] = mapped_column(String(10), index=True)
    message: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    structured_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(nullable=True)


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    detected_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    severity: Mapped[str] = mapped_column(String(10))
    source_alert_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    primary_affected_system: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column()
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    detector_name: Mapped[str] = mapped_column(String(80), index=True)
    detected_at: Mapped[datetime] = mapped_column(index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(80))
    metric_name: Mapped[str] = mapped_column(String(80))
    observed_value: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    expected_value: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    anomaly_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String(10))
    alert_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    raw_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column()
    reliability_score: Mapped[float] = mapped_column(default=1.0)
    structured_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    agent_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    started_at: Mapped[datetime] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    model_name: Mapped[str] = mapped_column(String(60))
    tool_call_count: Mapped[int] = mapped_column(default=0)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    trace_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    output: Mapped[Optional[dict[str, Any]]] = mapped_column(nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IncidentGroundTruth(Base):
    __tablename__ = "incident_ground_truth"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id"), primary_key=True
    )
    injected_incident_type: Mapped[str] = mapped_column(String(60))
    root_cause_code: Mapped[str] = mapped_column(String(60))
    root_cause_description: Mapped[str] = mapped_column(Text)
    affected_tables: Mapped[list[Any]] = mapped_column()
    affected_jobs: Mapped[list[Any]] = mapped_column()
    affected_reports: Mapped[list[Any]] = mapped_column()
    expected_evidence: Mapped[list[Any]] = mapped_column()
    should_escalate: Mapped[bool] = mapped_column(default=False)
    injection_manifest: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column()


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    historical_incident_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    incident_type: Mapped[str] = mapped_column(String(60))
    symptoms: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    affected_systems: Mapped[list[Any]] = mapped_column()
    remediation: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    evidence_summary: Mapped[str] = mapped_column(Text)
    searchable_text: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column()


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    evaluation_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    started_at: Mapped[datetime] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(20))
    model_name: Mapped[str] = mapped_column(String(60))
    configuration: Mapped[dict[str, Any]] = mapped_column()
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(nullable=True)
    report_path: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class StagingRecord(Base):
    """Raw ingested records before validation.

    Lets us simulate null-contamination, partial-load and schema-change incidents in the staging
    zone without violating the curated core schema (see docs/SECURITY.md / CLAUDE.md rule 9).
    """

    __tablename__ = "staging_records"

    staging_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    source_system: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    natural_key: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column()
    load_status: Mapped[str] = mapped_column(String(20), default="loaded")
    ingested_at: Mapped[datetime] = mapped_column(index=True)


class SchemaEvent(Base):
    """A simulated source schema-contract change (renamed/dropped/retyped field).

    Represented as metadata + logs rather than real DDL so the environment stays recoverable.
    """

    __tablename__ = "schema_events"

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    table_name: Mapped[str] = mapped_column(String(60), index=True)
    change_type: Mapped[str] = mapped_column(String(40))
    field_name: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text)
    pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(index=True)
