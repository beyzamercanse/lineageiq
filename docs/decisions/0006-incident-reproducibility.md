# ADR-0006: Incident reproducibility via seed + manifest

## Status
Accepted

## Context
Evaluation must be repeatable: injecting the same incident must produce the same data changes, and
the clean baseline must be restorable between cases.

## Decision
Every incident has a manifest (id, type, seed, target selectors, expected outcomes). Injectors are
pure functions of (clean data, seed, manifest). Restore is deterministic regeneration of the clean
baseline from the global seed; an optional snapshot can short-circuit regeneration.

## Consequences
- Any incident can be reproduced byte-for-byte from its manifest.
- Evaluation isolates one root cause at a time against a fresh baseline.
