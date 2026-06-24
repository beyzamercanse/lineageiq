.DEFAULT_GOAL := help
SHELL := /bin/bash

# Use the active python; override with `make PY=python3.12 ...`
PY ?= python3
PIP ?= $(PY) -m pip

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

## ---- Setup ----
install: ## Install backend (editable+dev) and frontend deps
	$(PIP) install -e ".[dev]"
	cd frontend && npm install

dev: ## Run backend (uvicorn) — frontend: `make dev-frontend`
	cd backend && $(PY) -m uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run the Next.js dev server
	cd frontend && npm run dev

## ---- Quality ----
test: ## Run all tests
	$(PY) -m pytest

test-unit: ## Run unit tests
	$(PY) -m pytest -m unit

test-integration: ## Run integration tests
	$(PY) -m pytest -m integration

lint: ## Ruff lint
	$(PY) -m ruff check backend

format: ## Ruff format + autofix
	$(PY) -m ruff format backend
	$(PY) -m ruff check --fix backend

typecheck: ## mypy
	$(PY) -m mypy

## ---- Database / data ----
migrate: ## Apply Alembic migrations
	cd backend && $(PY) -m alembic upgrade head

reset-db: ## Drop + recreate all tables (DESTRUCTIVE)
	$(PY) -m app.db.cli reset

seed: ## Generate the clean synthetic AtlasCommerce dataset
	$(PY) -m app.simulator.cli seed

validate-data: ## Assert clean-baseline invariants hold
	$(PY) -m app.simulator.cli validate

## ---- Incidents (Phase 2+) ----
generate-incidents: ## Generate the 80 incident manifests
	$(PY) -m app.incidents.cli generate

inject-incident: ## Inject one incident: make inject-incident INCIDENT_ID=<id>
	$(PY) -m app.incidents.cli inject --incident-id $(INCIDENT_ID)

restore-clean-data: ## Restore the clean baseline
	$(PY) -m app.incidents.cli restore

detect: ## Run deterministic detection controls
	$(PY) -m app.detection.cli run

investigate: ## Investigate one incident: make investigate INCIDENT_ID=<id>
	$(PY) -m app.agent.cli investigate --incident-id $(INCIDENT_ID)

evaluate: ## Run the evaluation suite
	$(PY) -m app.evaluation.cli run

## ---- Demo ----
demo: ## Prepare the full stale-FX demonstration environment
	$(PY) -m app.simulator.cli seed
	$(PY) -m app.incidents.cli generate
	$(PY) -m app.incidents.cli inject --incident-type stale_fx_rate --first
	$(PY) -m app.detection.cli run
	@echo "Demo environment ready. Start the API with 'make dev'."

# Note: make targets cd into backend via PYTHONPATH set in pyproject pytest config;
# app.* modules are importable when run from ./backend. The recipes below export it.
export PYTHONPATH := backend:$(PYTHONPATH)
