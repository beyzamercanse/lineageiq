# ADR-0005: Postgres in production, SQLite-compatible for local verification

## Status
Accepted

## Context
The spec targets PostgreSQL, but contributors (and CI smoke runs) benefit from being able to seed,
validate, and test without a running Postgres.

## Decision
Use SQLAlchemy 2 with portable column types (`JSON`, `Numeric`, timezone-aware `DateTime`). The
app reads `DATABASE_URL`; `postgresql+psycopg://...` is the default, `sqlite:///...` is supported
for local/dev/test. Postgres-only hardening (read-only role, statement timeout) is applied when
the dialect is Postgres and skipped gracefully on SQLite.

## Consequences
- Fast local iteration and offline tests.
- A small amount of dialect-aware code in the DB/session layer.
