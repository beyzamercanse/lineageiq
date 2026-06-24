"""run_readonly_sql: parameterized, SELECT-only SQL with allowlist + row cap + timeout."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.sql_guard import validate_and_wrap_sql


class RunReadonlySqlTool(Tool):
    name = "run_readonly_sql"
    description = (
        "Run a single read-only SELECT (CTEs allowed) against allowlisted tables. "
        "Returns bounded result rows. No writes, no DDL, no multiple statements."
    )
    evidence_type = "sql"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        query: str = kwargs.get("query", "")
        reason: str = kwargs.get("reason", "")
        params: dict[str, Any] = kwargs.get("params", {}) or {}
        settings = get_settings()
        dialect = "postgres" if settings.is_postgres else "sqlite"

        wrapped = validate_and_wrap_sql(
            query,
            row_limit=settings.sql_row_limit,
            max_length=settings.sql_max_query_length,
            dialect=dialect,
        )

        # Best-effort statement timeout on Postgres.
        if settings.is_postgres:
            import contextlib

            with contextlib.suppress(Exception):  # pragma: no cover - dialect dependent
                ctx.session.execute(
                    text("SET LOCAL statement_timeout = :ms"),
                    {"ms": settings.sql_timeout_seconds * 1000},
                )

        start = time.perf_counter()
        result = ctx.session.execute(text(wrapped), params)
        columns = list(result.keys())
        rows = result.fetchall()
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        truncated = len(rows) > settings.sql_row_limit
        rows = rows[: settings.sql_row_limit]
        row_dicts = [dict(zip(columns, [_jsonable(v) for v in r])) for r in rows]

        payload = {
            "reason": reason,
            "query": query,
            "columns": columns,
            "rows": row_dicts,
            "row_count": len(row_dicts),
            "truncated": truncated,
            "execution_ms": round(elapsed_ms, 2),
        }
        summary = (
            f"SQL returned {len(row_dicts)} row(s)"
            + (" (truncated)" if truncated else "")
            + (f"; reason: {reason}" if reason else "")
        )
        return self._result(ctx, summary, payload)


def _jsonable(value: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
