"""Lineage API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.errors import NotFoundError
from app.lineage.service import get_lineage_store
from app.lineage.types import LineageNode, LineageQueryResult, NodeType

router = APIRouter(prefix="/lineage", tags=["lineage"])


@router.get("/nodes", response_model=list[LineageNode])
def list_nodes(node_type: NodeType | None = Query(default=None)) -> list[LineageNode]:
    """List lineage nodes, optionally filtered by type."""
    return get_lineage_store().all_nodes(node_type)


@router.get("/impact", response_model=LineageQueryResult)
def impact(
    node_id: str = Query(..., description="Node whose downstream impact to compute"),
    max_depth: int = Query(default=10, ge=1, le=20),
) -> LineageQueryResult:
    """Downstream impact: what is affected if this node fails?"""
    store = get_lineage_store()
    if store.get_node(node_id) is None:
        raise NotFoundError(f"Lineage node not found: {node_id}")
    return store.impact(node_id, max_depth=max_depth)


@router.get("/upstream", response_model=LineageQueryResult)
def upstream(
    node_id: str = Query(...),
    max_depth: int = Query(default=6, ge=1, le=20),
) -> LineageQueryResult:
    """What feeds this node?"""
    store = get_lineage_store()
    if store.get_node(node_id) is None:
        raise NotFoundError(f"Lineage node not found: {node_id}")
    return store.upstream(node_id, max_depth=max_depth)


@router.get("/path", response_model=LineageQueryResult)
def path(
    source: str = Query(...),
    target: str = Query(...),
) -> LineageQueryResult:
    """Shortest dependency path between two nodes."""
    store = get_lineage_store()
    for n in (source, target):
        if store.get_node(n) is None:
            raise NotFoundError(f"Lineage node not found: {n}")
    nodes_path = store.shortest_path(source, target)
    if nodes_path is None:
        return LineageQueryResult(root=source, direction="path", nodes=[], edges=[], paths=[])
    nodes = [store.get_node(n) for n in nodes_path]
    edges = [
        e for e in store.all_edges()
        if any(e.source == a and e.target == b for a, b in zip(nodes_path, nodes_path[1:]))
    ]
    return LineageQueryResult(
        root=source, direction="path",
        nodes=[n for n in nodes if n is not None], edges=edges, paths=[nodes_path],
    )
