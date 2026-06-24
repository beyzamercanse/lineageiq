"""inspect_pipeline_runs: examine pipeline runs for delays, failures, row-count drift."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.models import PipelineRun
from app.tools.base import Tool, ToolContext, ToolResult


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class InspectPipelineRunsTool(Tool):
    name = "inspect_pipeline_runs"
    description = "Inspect pipeline runs (by pipeline / time range / status): delays and failures."
    evidence_type = "pipeline"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        pipeline = kwargs.get("pipeline")
        start = _parse_dt(kwargs.get("start_time"))
        end = _parse_dt(kwargs.get("end_time"))
        status = kwargs.get("status")
        max_results = min(int(kwargs.get("max_results", 50)), 200)

        stmt = select(PipelineRun)
        if pipeline:
            pid = pipeline if pipeline.startswith("PL-") else f"PL-{pipeline}"
            stmt = stmt.where(PipelineRun.pipeline_id == pid)
        if start is not None:
            stmt = stmt.where(PipelineRun.started_at >= start)
        if end is not None:
            stmt = stmt.where(PipelineRun.started_at <= end)
        if status:
            stmt = stmt.where(PipelineRun.status == status)
        stmt = stmt.order_by(PipelineRun.started_at).limit(max_results)

        runs = list(ctx.session.execute(stmt).scalars())
        records = []
        failures = 0
        delays = 0
        for r in runs:
            duration_h = None
            if r.completed_at is not None:
                duration_h = round((r.completed_at - r.started_at).total_seconds() / 3600.0, 2)
            if r.status in ("failed",):
                failures += 1
            if r.status == "delayed" or (duration_h is not None and duration_h > 3):
                delays += 1
            records.append({
                "pipeline_run_id": r.pipeline_run_id,
                "pipeline_id": r.pipeline_id,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "status": r.status,
                "rows_read": r.rows_read,
                "rows_written": r.rows_written,
                "duration_hours": duration_h,
                "error_message": r.error_message,
            })

        payload = {
            "pipeline": pipeline, "runs": records,
            "failure_count": failures, "delayed_count": delays,
        }
        summary = (
            f"{len(records)} run(s) for {pipeline or 'all pipelines'}: "
            f"{failures} failed, {delays} delayed"
        )
        return self._result(ctx, summary, payload)
