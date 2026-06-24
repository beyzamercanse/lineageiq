"""Default registry of all read-only agent tools."""

from __future__ import annotations

from app.tools.base import ToolRegistry
from app.tools.historical_tool import SearchHistoricalIncidentsTool
from app.tools.lineage_tool import QueryLineageTool
from app.tools.log_tool import SearchLogsTool
from app.tools.pipeline_tool import InspectPipelineRunsTool
from app.tools.schema_tool import InspectSchemaTool
from app.tools.sql_tool import RunReadonlySqlTool


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        RunReadonlySqlTool(),
        SearchLogsTool(),
        QueryLineageTool(),
        SearchHistoricalIncidentsTool(),
        InspectPipelineRunsTool(),
        InspectSchemaTool(),
    ):
        registry.register(tool)
    return registry
