"""Lineage node/edge types and query-result DTOs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    SYSTEM = "system"
    API = "api"
    DATABASE = "database"
    TABLE = "table"
    COLUMN = "column"
    PIPELINE = "pipeline"
    JOB = "job"
    REPORT = "report"
    DASHBOARD = "dashboard"
    BUSINESS_METRIC = "business_metric"


class EdgeType(str, Enum):
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    TRANSFORMS = "transforms"
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    PUBLISHES = "publishes"
    MAPS_TO = "maps_to"
    AGGREGATES_INTO = "aggregates_into"


# Assets that count as "impacted downstream business outputs".
IMPACT_ASSET_TYPES = {NodeType.REPORT, NodeType.DASHBOARD, NodeType.BUSINESS_METRIC}


class LineageNode(BaseModel):
    id: str
    type: NodeType
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    source: str
    target: str
    type: EdgeType


class LineageQueryResult(BaseModel):
    """Result of a traversal: relevant nodes, edges, paths, and impacted assets."""

    root: str
    direction: str
    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdge] = Field(default_factory=list)
    paths: list[list[str]] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
