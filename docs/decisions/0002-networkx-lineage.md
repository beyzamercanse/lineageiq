# ADR-0002: NetworkX for the lineage graph (Neo4j-ready)

## Status
Accepted

## Context
Lineage needs upstream/downstream traversal, shortest path, and impact analysis. A full graph DB
(Neo4j) adds operational weight not justified for an MVP.

## Decision
Implement a `LineageStore` interface and back it with NetworkX (`NetworkXLineageStore`). The graph
is defined in version-controlled config. The agent-facing API depends only on the interface.

## Consequences
- Fast to build and test, no extra service.
- Neo4j can be added later as another `LineageStore` implementation without changing the agent or
  API. Graph metadata is also persisted in Postgres.
