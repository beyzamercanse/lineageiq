# LineageIQ — Task Checklist

Legend: `[x]` done · `[~]` in progress · `[ ]` todo

## Phase 0 — Foundation
- [x] Planning docs (PLAN, ARCHITECTURE, DATA_MODEL, AGENT_DESIGN, EVALUATION, SECURITY, DEMO)
- [x] CLAUDE.md project rules
- [x] ADRs 0001–0006
- [x] Repo skeleton
- [x] `.gitignore`, `.env.example`
- [x] `pyproject.toml` (Ruff, mypy, pytest config)
- [x] Backend core config (`app/core/config.py`), settings via env
- [x] DB session/engine layer (Postgres + SQLite), `app/db/`
- [x] Structured JSON logging + correlation IDs
- [x] FastAPI app + `/api/v1/health`, `/api/v1/system/status`
- [x] Frontend Next.js shell that loads + calls health
- [x] Docker Compose (postgres, backend, frontend, otel-collector, jaeger)
- [x] Makefile with documented commands
- [x] GitHub Actions CI (lint, typecheck, unit, integration, docker build)
- [x] Smoke tests pass (`test_health`)

## Phase 1 — Clean synthetic enterprise environment
- [x] SQLAlchemy models for all business + operational tables
- [x] Alembic env + initial migration (autogenerate-compatible)
- [x] Deterministic generator: customers, CRM, mappings, limits
- [x] Generator: orders, payments, refunds, shipments
- [x] Generator: daily FX rates, daily revenue reports
- [x] Generator: pipeline definitions + runs + logs
- [x] Clean-baseline validation suite (`make validate-data`)
- [x] `make reset-db`, `make seed`, `make validate-data`
- [x] Determinism test (same seed ⇒ identical data)
- [x] Unit tests for generator + validation

## Phase 2 — Incident injection + deterministic detection
- [x] Shared taxonomy (10 incident types, 11 root-cause codes, severity)
- [x] Incident manifest model + JSON persistence
- [x] 10 injector classes (schema-change simulated via staging/metadata/logs, no DDL)
- [x] Manifest generator (80 incidents: 8 per type)
- [x] Restore clean baseline (deterministic regeneration)
- [x] 11 deterministic detection controls producing standardized `Alert`
- [x] Severity scoring (`detection/severity.py`)
- [x] Alert → incident creation + initial evidence + ground truth
- [x] `make generate-incidents`, `make inject-incident`, `make restore-clean-data`, `make detect`
- [x] Tests: per-injector (deterministic, isolated), per-category detector firing, pipeline integration
- [x] Stale-FX demo verified end to end (ruff + mypy + 56 tests green)

## Phase 3 — Lineage graph + impact analysis
- [ ] LineageStore interface + NetworkX impl
- [ ] AtlasCommerce lineage config + traversal/impact
- [ ] Lineage API + basic frontend explorer

## Phase 4 — ML components
- [ ] Feature pipelines, Isolation Forest, classifier+calibration, TF-IDF clustering, persistence

## Phase 5 — Agent tools + orchestration
- [ ] 6 read-only tools, bounded agent, structured output, evidence persistence, FakeLLM
- [ ] Deterministic stale-FX demo

## Phase 6 — Grounding/validation/human-review
- [ ] Unsupported-claim detector, evidence validation, escalation policy

## Phase 7 — Full API + frontend pages
- [ ] Incident queue, detail, lineage explorer, eval dashboard, demo controls

## Phase 8 — Evaluation + observability
- [ ] Evaluation runner + metrics + automated baseline + tracing + cost + eval UI

## Phase 9 — Portfolio polish
- [ ] Final README with generated results, screenshots, limitations, clean setup
