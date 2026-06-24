"""Restore the clean baseline by deterministic regeneration (ADR-0006)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset


def restore_clean_baseline(
    session: Session, config: GeneratorConfig | None = None
) -> dict[str, int]:
    """Wipe all data and regenerate the deterministic clean baseline."""
    if config is None:
        config = GeneratorConfig(seed=get_settings().random_seed)
    return generate_clean_dataset(session, config)
