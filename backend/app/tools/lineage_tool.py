"""query_lineage: traverse the lineage graph from a node."""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolContext, ToolResult


class QueryLineageTool(Tool):
    name = "query_lineage"
    description = "Traverse data lineage upstream/downstream from a node; returns impacted assets."
    evidence_type = "lineage"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        start_node: str = kwargs.get("start_node", "")
        direction: str = kwargs.get("direction", "downstream")
        max_depth = int(kwargs.get("max_depth", 6))

        if ctx.lineage.get_node(start_node) is None:
            return ToolResult(
                evidence_id=self._persist_evidence(
                    ctx, f"Unknown lineage node: {start_node}",
                    {"start_node": start_node, "error": "unknown_node"},
                ),
                tool_name=self.name, summary=f"Unknown lineage node: {start_node}",
                payload={"start_node": start_node}, error="unknown_node",
            )

        if direction == "upstream":
            result = ctx.lineage.upstream(start_node, max_depth=max_depth)
        else:
            result = ctx.lineage.downstream(start_node, max_depth=max_depth)

        payload = {
            "start_node": start_node,
            "direction": direction,
            "nodes": [n.model_dump(mode="json") for n in result.nodes],
            "edges": [e.model_dump(mode="json") for e in result.edges],
            "paths": result.paths,
            "affected_assets": result.affected_assets,
        }
        summary = (
            f"Lineage {direction} of {start_node}: {len(result.nodes)} nodes, "
            f"affected assets: {result.affected_assets}"
        )
        return self._result(ctx, summary, payload)
