"""search_logs: bounded search over system logs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.models import SystemLog
from app.tools.base import Tool, ToolContext, ToolResult

_MAX = 100


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class SearchLogsTool(Tool):
    name = "search_logs"
    description = "Search application/pipeline logs by service, time range, terms, and levels."
    evidence_type = "log"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        service = kwargs.get("service")
        start = _parse_dt(kwargs.get("start_time"))
        end = _parse_dt(kwargs.get("end_time"))
        terms = [t.lower() for t in (kwargs.get("search_terms") or [])]
        levels = kwargs.get("log_levels") or []
        max_results = min(int(kwargs.get("max_results", 50)), _MAX)

        stmt = select(SystemLog)
        if service:
            stmt = stmt.where(SystemLog.service == service)
        if start is not None:
            stmt = stmt.where(SystemLog.timestamp >= start)
        if end is not None:
            stmt = stmt.where(SystemLog.timestamp <= end)
        if levels:
            stmt = stmt.where(SystemLog.log_level.in_(levels))
        stmt = stmt.order_by(SystemLog.timestamp).limit(500)

        matched = []
        for log in ctx.session.execute(stmt).scalars():
            if terms and not any(t in log.message.lower() for t in terms):
                continue
            matched.append(log)

        truncated = len(matched) > max_results
        matched = matched[:max_results]
        severity_counts = Counter(log.log_level for log in matched)
        correlated = sorted({log.pipeline_run_id for log in matched if log.pipeline_run_id})

        payload = {
            "service": service,
            "records": [
                {
                    "log_id": log.log_id,
                    "timestamp": log.timestamp.isoformat(),
                    "service": log.service,
                    "level": log.log_level,
                    "message": log.message,
                    "pipeline_run_id": log.pipeline_run_id,
                }
                for log in matched
            ],
            "counts_by_level": dict(severity_counts),
            "correlated_pipeline_runs": correlated,
            "truncated": truncated,
        }
        summary = (
            f"Found {len(matched)} log record(s)"
            + (f" for service={service}" if service else "")
            + f"; levels={dict(severity_counts)}"
        )
        return self._result(ctx, summary, payload)
