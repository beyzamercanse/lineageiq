# ADR-0004: Decimal money, UTC time

## Status
Accepted

## Context
Financial reconciliation must be exact; floating point introduces rounding errors. Multi-timezone
source systems must not corrupt stored timestamps.

## Decision
Store money as SQL `NUMERIC(18,4)` mapped to Python `Decimal`. Store all timestamps in UTC
(`DateTime(timezone=True)`). Source-system local time is represented only as data, never as the
stored canonical time.

## Consequences
Reconciliation is exact and reproducible. Timezone-conversion incidents are simulated as data, not
as storage bugs.
