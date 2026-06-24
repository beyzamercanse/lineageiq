"""search_historical_incidents: TF-IDF similarity search over prior incidents."""

from __future__ import annotations

from typing import Any

from app.ml.historical import HistoricalIndex
from app.tools.base import Tool, ToolContext, ToolResult


class SearchHistoricalIncidentsTool(Tool):
    name = "search_historical_incidents"
    description = "Find similar historical incidents by symptoms / affected systems / type."
    evidence_type = "historical"

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        symptoms: str = kwargs.get("symptoms", "")
        affected_systems = kwargs.get("affected_systems") or []
        suspected_type = kwargs.get("suspected_incident_type", "")
        max_results = int(kwargs.get("max_results", 5))

        index = ctx.historical or HistoricalIndex().fit(ctx.session)
        query = " ".join([symptoms, " ".join(affected_systems), suspected_type]).strip()
        matches = index.search(query, k=max_results)

        payload = {
            "query": query,
            "matches": [
                {
                    "historical_incident_id": m.historical_incident_id,
                    "score": round(m.score, 4),
                    "incident_type": m.incident_type,
                    "title": m.title,
                    "root_cause": m.root_cause,
                    "remediation": m.remediation,
                    "cluster": m.cluster,
                }
                for m in matches
            ],
        }
        top = matches[0].incident_type if matches else "none"
        summary = f"Top historical match: {top} ({len(matches)} candidates)"
        return self._result(ctx, summary, payload)
