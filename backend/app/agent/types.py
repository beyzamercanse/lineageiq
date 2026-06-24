"""Agent control types: tool invocations, decisions, and investigation context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.taxonomy import RootCauseCode, Severity


@dataclass
class ToolInvocation:
    tool_name: str
    args: dict[str, Any]
    reason: str


@dataclass
class AgentDecision:
    """Either invoke a tool or finalize the investigation."""

    finalize: bool
    invocation: ToolInvocation | None = None


@dataclass
class CollectedEvidence:
    evidence_id: str
    tool_name: str
    summary: str
    payload: dict[str, Any]
    evidence_type: str


@dataclass
class InvestigationContext:
    incident_id: str
    title: str
    severity: Severity
    suspected_root_cause: RootCauseCode
    primary_system: str
    focus_node: str | None
    alert_meta: dict[str, Any] = field(default_factory=dict)
    initial_evidence_ids: list[str] = field(default_factory=list)
    collected: list[CollectedEvidence] = field(default_factory=list)
    max_tool_calls: int = 8

    @property
    def remaining_tool_calls(self) -> int:
        return self.max_tool_calls - len(self.collected)
