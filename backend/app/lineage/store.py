"""LineageStore interface + NetworkX implementation.

The agent-facing API depends only on ``LineageStore`` so a Neo4j-backed implementation can replace
NetworkX later without touching callers (ADR-0002).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import networkx as nx

from app.lineage.types import (
    IMPACT_ASSET_TYPES,
    LineageEdge,
    LineageNode,
    LineageQueryResult,
    NodeType,
)

_MAX_PATHS = 25


class LineageStore(ABC):
    """Abstract lineage graph store."""

    @abstractmethod
    def add_node(self, node: LineageNode) -> None: ...

    @abstractmethod
    def add_edge(self, edge: LineageEdge) -> None: ...

    @abstractmethod
    def get_node(self, node_id: str) -> LineageNode | None: ...

    @abstractmethod
    def all_nodes(self, node_type: NodeType | None = None) -> list[LineageNode]: ...

    @abstractmethod
    def all_edges(self) -> list[LineageEdge]: ...

    @abstractmethod
    def upstream(self, node_id: str, max_depth: int = 6) -> LineageQueryResult: ...

    @abstractmethod
    def downstream(self, node_id: str, max_depth: int = 6) -> LineageQueryResult: ...

    @abstractmethod
    def shortest_path(self, source: str, target: str) -> list[str] | None: ...

    @abstractmethod
    def impact(self, node_id: str, max_depth: int = 10) -> LineageQueryResult: ...

    @abstractmethod
    def to_dict(self) -> dict: ...


class NetworkXLineageStore(LineageStore):
    """Directed-graph lineage store. Edges point in the direction of data flow."""

    def __init__(self) -> None:
        self._g = nx.DiGraph()

    def add_node(self, node: LineageNode) -> None:
        self._g.add_node(node.id, node=node)

    def add_edge(self, edge: LineageEdge) -> None:
        if edge.source not in self._g or edge.target not in self._g:
            raise ValueError(f"Edge references unknown node: {edge.source}->{edge.target}")
        self._g.add_edge(edge.source, edge.target, type=edge.type)

    def get_node(self, node_id: str) -> LineageNode | None:
        data = self._g.nodes.get(node_id)
        return data["node"] if data else None

    def all_nodes(self, node_type: NodeType | None = None) -> list[LineageNode]:
        nodes = [data["node"] for _, data in self._g.nodes(data=True)]
        if node_type is not None:
            nodes = [n for n in nodes if n.type == node_type]
        return sorted(nodes, key=lambda n: n.id)

    def all_edges(self) -> list[LineageEdge]:
        return [
            LineageEdge(source=u, target=v, type=d["type"])
            for u, v, d in self._g.edges(data=True)
        ]

    def _require(self, node_id: str) -> None:
        if node_id not in self._g:
            raise KeyError(f"Unknown lineage node: {node_id}")

    def _subgraph_result(
        self, node_id: str, graph: nx.DiGraph, direction: str, max_depth: int
    ) -> LineageQueryResult:
        ego = nx.ego_graph(graph, node_id, radius=max_depth)
        node_ids = set(ego.nodes)
        nodes = [self._g.nodes[n]["node"] for n in node_ids]
        edges = [
            LineageEdge(source=u, target=v, type=self._g.edges[u, v]["type"])
            if graph is self._g
            else LineageEdge(source=v, target=u, type=self._g.edges[v, u]["type"])
            for u, v in ego.edges
        ]
        # Representative paths from node to boundary (leaves of the ego graph).
        leaves = [n for n in node_ids if n != node_id and ego.out_degree(n) == 0]
        paths: list[list[str]] = []
        for leaf in sorted(leaves):
            for path in nx.all_simple_paths(ego, node_id, leaf, cutoff=max_depth):
                # Translate reversed-graph paths back to data-flow direction.
                paths.append(path if graph is self._g else list(reversed(path)))
                if len(paths) >= _MAX_PATHS:
                    break
            if len(paths) >= _MAX_PATHS:
                break
        affected = sorted(
            n for n in node_ids
            if n != node_id and self._g.nodes[n]["node"].type in IMPACT_ASSET_TYPES
        )
        return LineageQueryResult(
            root=node_id, direction=direction,
            nodes=sorted(nodes, key=lambda n: n.id), edges=edges,
            paths=paths, affected_assets=affected,
        )

    def downstream(self, node_id: str, max_depth: int = 6) -> LineageQueryResult:
        self._require(node_id)
        return self._subgraph_result(node_id, self._g, "downstream", max_depth)

    def upstream(self, node_id: str, max_depth: int = 6) -> LineageQueryResult:
        self._require(node_id)
        return self._subgraph_result(node_id, self._g.reverse(copy=False), "upstream", max_depth)

    def shortest_path(self, source: str, target: str) -> list[str] | None:
        self._require(source)
        self._require(target)
        try:
            return nx.shortest_path(self._g, source, target)
        except nx.NetworkXNoPath:
            return None

    def impact(self, node_id: str, max_depth: int = 10) -> LineageQueryResult:
        result = self.downstream(node_id, max_depth=max_depth)
        result.direction = "impact"
        return result

    def to_dict(self) -> dict:
        return {
            "nodes": [n.model_dump(mode="json") for n in self.all_nodes()],
            "edges": [e.model_dump(mode="json") for e in self.all_edges()],
        }
