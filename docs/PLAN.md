# LineageIQ — Implementation Plan

## Goal

Build a working end-to-end root-cause investigation platform for a synthetic multi-system
company (AtlasCommerce), demonstrating: enterprise data modeling, reconciliation, data lineage,
anomaly detection, applied ML, safe LLM tool use, evidence-grounded reasoning, human-in-the-loop
design, model evaluation, API engineering, frontend product thinking, observability, testing,
and security awareness.

## Strategy

Build a **complete vertical slice** that works end to end, then deepen each layer. Prefer
correctness and determinism over novelty. Every phase keeps the app runnable.

## Phases (see TASKS.md for the live checklist)

- **Phase 0 — Foundation:** repo skeleton, config, Docker Compose, DB connection, health
  endpoint, frontend shell, CI. *Status: done.*
- **Phase 1 — Clean synthetic environment:** SQLAlchemy models, Alembic migrations,
  deterministic generator, clean-baseline validation, pipeline runs, logs, revenue reports.
- **Phase 2 — Incident injection + deterministic detection:** manifests, 10 injectors,
  80 incidents, restore, deterministic controls, alerts, incident creation.
- **Phase 3 — Lineage graph + impact analysis.**
- **Phase 4 — ML components** (Isolation Forest, severity/classifier, calibration, TF-IDF).
- **Phase 5 — Agent tools + bounded investigation orchestration + FakeLLM.**
- **Phase 6 — Grounding, validation, human-review policy.**
- **Phase 7 — Full API + frontend pages.**
- **Phase 8 — Evaluation runner + observability + automated baseline.**
- **Phase 9 — Portfolio polish.**

## Key design decisions

- NetworkX for the lineage graph in the MVP, behind a `LineageStore` interface so Neo4j can be
  swapped in later without changing the agent-facing API. (ADR-0002)
- Provider-independent LLM interface with a deterministic FakeLLM for tests. (ADR-0003)
- Decimal money everywhere; UTC timestamps. (ADR-0004)
- DB layer is SQLAlchemy 2 targeting Postgres, written to also run on SQLite for fast local
  verification. (ADR-0005)
- Incident reproducibility via deterministic regeneration from a seed + manifest, plus an
  optional clean snapshot. (ADR-0006)

## Definition of done

See spec §30 — a user can seed, inject, detect, investigate, inspect evidence, view ranked root
causes + lineage impact + human-review status, run evaluation with real metrics, reproduce the
stale-FX demo, and run all tests without a paid LLM API.
