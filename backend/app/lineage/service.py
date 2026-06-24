"""Lineage service: a process-wide cached store + convenience queries."""

from __future__ import annotations

from functools import lru_cache

from app.lineage.graph_config import ROOT_CAUSE_FOCUS_NODE, build_atlas_lineage
from app.lineage.store import LineageStore
from app.lineage.types import LineageQueryResult


@lru_cache
def get_lineage_store() -> LineageStore:
    """Return the cached AtlasCommerce lineage store."""
    return build_atlas_lineage()


def impact_of(node_id: str, max_depth: int = 10) -> LineageQueryResult:
    return get_lineage_store().impact(node_id, max_depth=max_depth)


def focus_node_for(root_cause: str) -> str | None:
    """Map a root-cause code value to its lineage focus node, if known."""
    from app.core.taxonomy import RootCauseCode

    try:
        return ROOT_CAUSE_FOCUS_NODE.get(RootCauseCode(root_cause))
    except ValueError:
        return None
