"""Bounded investigation orchestrator.

Drives an LLMClient over registered read-only tools within strict budgets, persists an AgentRun and
all evidence, and returns a validated structured InvestigationReport.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import LLMClient, get_llm
from app.agent.policy import evaluate_human_review
from app.agent.types import CollectedEvidence, InvestigationContext
from app.agent.validation import validate_report
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.taxonomy import RootCauseCode, Severity
from app.lineage.service import focus_node_for, get_lineage_store
from app.ml.historical import HistoricalIndex
from app.models import AgentRun, Evidence, Incident
from app.observability.tracing import span
from app.schemas.investigation import InvestigationReport
from app.tools.base import ToolContext
from app.tools.registry import build_default_registry

log = get_logger(__name__)

_META_KEYS = ("date", "currency", "region", "table", "field", "next_date", "count", "service")


@dataclass
class AgentBudget:
    max_tool_calls: int
    max_duration_seconds: int

    @classmethod
    def from_settings(cls) -> AgentBudget:
        s = get_settings()
        return cls(s.agent_max_tool_calls, s.agent_max_duration_seconds)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_context(
    session: Session, incident: Incident, max_tool_calls: int
) -> InvestigationContext:
    """Build the initial investigation context from the incident's alert evidence."""
    alert_ev = list(session.execute(
        select(Evidence).where(
            Evidence.incident_id == incident.incident_id,
            Evidence.evidence_type == "alert",
        )
    ).scalars())

    causes: list[str] = []
    for e in alert_ev:
        payload = e.structured_payload or {}
        cause = payload.get("suspected_root_cause", RootCauseCode.UNKNOWN.value)
        causes.append(cause)
    named = [c for c in causes if c != RootCauseCode.UNKNOWN.value]
    leading_value = Counter(named).most_common(1)[0][0] if named else RootCauseCode.UNKNOWN.value
    leading = RootCauseCode(leading_value)

    alert_meta: dict = {}
    for e in alert_ev:
        payload = e.structured_payload or {}
        if payload.get("suspected_root_cause") == leading_value:
            for k in _META_KEYS:
                if k in payload and k not in alert_meta:
                    alert_meta[k] = payload[k]

    return InvestigationContext(
        incident_id=incident.incident_id,
        title=incident.title,
        severity=Severity(incident.severity),
        suspected_root_cause=leading,
        primary_system=incident.primary_affected_system or "Reporting",
        focus_node=focus_node_for(leading_value),
        alert_meta=alert_meta,
        initial_evidence_ids=[e.evidence_id for e in alert_ev],
        max_tool_calls=max_tool_calls,
    )


def investigate_incident(
    session: Session,
    incident_id: str,
    *,
    llm: LLMClient | None = None,
    budget: AgentBudget | None = None,
) -> InvestigationReport:
    """Run a bounded investigation and persist the AgentRun + evidence."""
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise KeyError(f"Incident not found: {incident_id}")

    llm = llm or get_llm()
    budget = budget or AgentBudget.from_settings()
    registry = build_default_registry()
    lineage = get_lineage_store()
    historical = HistoricalIndex().fit(session)
    tool_ctx = ToolContext(
        session=session, incident_id=incident_id, lineage=lineage, historical=historical,
    )

    run_id = f"RUN-{uuid.uuid4().hex[:10]}"
    trace_id = uuid.uuid4().hex
    started = _now()
    agent_run = AgentRun(
        agent_run_id=run_id, incident_id=incident_id, started_at=started,
        status="running", model_name=llm.model_name, trace_id=trace_id,
    )
    session.add(agent_run)
    session.flush()

    context = build_context(session, incident, budget.max_tool_calls)
    budget_exhausted = False

    with span("agent.investigate", incident_id=incident_id, agent_run_id=run_id):
        while True:
            if len(context.collected) >= budget.max_tool_calls:
                budget_exhausted = True
                break
            if (_now() - started).total_seconds() > budget.max_duration_seconds:
                budget_exhausted = True
                break
            decision = llm.decide(context)
            if decision.finalize or decision.invocation is None:
                break
            inv = decision.invocation
            try:
                tool = registry.get(inv.tool_name)
                result = tool.run(tool_ctx, **inv.args)
                context.collected.append(CollectedEvidence(
                    evidence_id=result.evidence_id, tool_name=result.tool_name,
                    summary=result.summary, payload=result.payload,
                    evidence_type=result.evidence_type,
                ))
            except Exception as exc:  # tool failed; record and continue
                log.warning("tool_failed", extra={"tool": inv.tool_name, "error": str(exc)})
                context.collected.append(CollectedEvidence(
                    evidence_id="", tool_name=inv.tool_name,
                    summary=f"Tool {inv.tool_name} failed: {exc}", payload={},
                    evidence_type="error",
                ))

        report = llm.synthesize(context)

    distinct_sources = len(
        {c.evidence_type for c in context.collected if c.evidence_type != "error"}
    )

    # Evidence-grounding / hallucination validation (deterministic).
    validation = validate_report(session, report)
    report.unsupported_claims = validation.unsupported_claims

    requires, reason = evaluate_human_review(
        report,
        distinct_evidence_sources=distinct_sources,
        severity=context.severity,
        budget_exhausted=budget_exhausted,
    )
    if not validation.passed:
        requires = True
        val_reason = "failed evidence validation"
        reason = f"{reason}; {val_reason}" if reason else val_reason
    report.requires_human_review = requires
    report.human_review_reason = reason

    agent_run.completed_at = _now()
    agent_run.status = "completed"
    agent_run.tool_call_count = len([c for c in context.collected if c.evidence_type != "error"])
    agent_run.prompt_tokens = llm.usage.prompt_tokens
    agent_run.completion_tokens = llm.usage.completion_tokens
    agent_run.estimated_cost = llm.usage.cost
    output = report.model_dump(mode="json")
    output["validation"] = validation.to_dict()
    agent_run.output = output
    session.flush()
    return report
