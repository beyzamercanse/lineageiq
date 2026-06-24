"""inspect_schema: report a table's columns/types/nullability + recent simulated schema events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.base import Base
from app.models import SchemaEvent
from app.tools.base import Tool, ToolContext, ToolResult


class InspectSchemaTool(Tool):
    name = "inspect_schema"
    description = "Inspect a table's columns, types, nullability, and recent schema-change events."
    evidence_type = "schema"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        table_name: str = kwargs.get("table", "")
        table = Base.metadata.tables.get(table_name)
        if table is None:
            return ToolResult(
                evidence_id=self._persist_evidence(
                    ctx, f"Unknown table: {table_name}",
                    {"table": table_name, "error": "unknown_table"},
                ),
                tool_name=self.name, summary=f"Unknown table: {table_name}",
                payload={"table": table_name}, error="unknown_table",
            )

        columns = [
            {
                "name": c.name,
                "type": str(c.type),
                "nullable": bool(c.nullable),
                "primary_key": bool(c.primary_key),
            }
            for c in table.columns
        ]
        events = list(ctx.session.execute(
            select(SchemaEvent).where(SchemaEvent.table_name == table_name)
            .order_by(SchemaEvent.occurred_at)
        ).scalars())
        event_payload = [
            {
                "event_id": e.event_id,
                "change_type": e.change_type,
                "field_name": e.field_name,
                "details": e.details,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ]

        payload = {
            "table": table_name,
            "schema_version": "v1",
            "columns": columns,
            "recent_schema_events": event_payload,
        }
        summary = (
            f"Table {table_name}: {len(columns)} columns; "
            f"{len(event_payload)} recent schema event(s)"
        )
        return self._result(ctx, summary, payload)
