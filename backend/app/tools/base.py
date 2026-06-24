"""Tool framework: context, result, base class, evidence persistence.

Every tool call validates inputs, is size-bounded, fails safely, and persists an Evidence record
tied to the incident so the agent's reasoning is always traceable.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.lineage.store import LineageStore
from app.ml.historical import HistoricalIndex
from app.models import Evidence
from app.observability.tracing import span

log = get_logger(__name__)


@dataclass
class ToolContext:
    """Shared dependencies + the incident a tool call belongs to."""

    session: Session
    incident_id: str
    lineage: LineageStore
    historical: HistoricalIndex | None = None


@dataclass
class ToolResult:
    evidence_id: str
    tool_name: str
    summary: str
    payload: dict[str, Any]
    reliability: float = 1.0
    evidence_type: str = "tool"
    error: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tool(ABC):
    """Base read-only tool."""

    name: str
    description: str
    evidence_type: str = "tool"

    @abstractmethod
    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a result (also persists an Evidence row)."""

    def _persist_evidence(
        self,
        ctx: ToolContext,
        summary: str,
        payload: dict[str, Any],
        *,
        reliability: float = 1.0,
        source: str | None = None,
    ) -> str:
        evidence_id = f"EV-{uuid.uuid4().hex[:10]}"
        ctx.session.add(Evidence(
            evidence_id=evidence_id,
            incident_id=ctx.incident_id,
            evidence_type=self.evidence_type,
            source=source or self.name,
            summary=summary[:4000],
            raw_reference=None,
            collected_at=_now(),
            reliability_score=reliability,
            structured_payload=payload,
        ))
        ctx.session.flush()
        return evidence_id

    def _result(
        self,
        ctx: ToolContext,
        summary: str,
        payload: dict[str, Any],
        *,
        reliability: float = 1.0,
    ) -> ToolResult:
        with span(f"tool.{self.name}", tool=self.name, incident_id=ctx.incident_id):
            evidence_id = self._persist_evidence(ctx, summary, payload, reliability=reliability)
        log.info("tool_call", extra={"tool": self.name, "incident_id": ctx.incident_id,
                                     "evidence_id": evidence_id})
        return ToolResult(
            evidence_id=evidence_id, tool_name=self.name, summary=summary,
            payload=payload, reliability=reliability, evidence_type=self.evidence_type,
        )


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name]

    def names(self) -> list[str]:
        return sorted(self.tools)
