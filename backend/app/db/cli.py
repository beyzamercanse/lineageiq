"""Database CLI: create/drop tables without Alembic (for local SQLite + tests).

Usage:
    python -m app.db.cli reset    # drop + create all tables
    python -m app.db.cli create   # create all tables
"""

from __future__ import annotations

import argparse
import os

from app.core.logging import configure_logging, get_logger
from app.db.session import get_engine
from app.models import Base  # noqa: F401  (ensures metadata is populated)

log = get_logger(__name__)


def create_all() -> None:
    engine = get_engine()
    # Ensure sqlite parent dir exists.
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:
        os.makedirs(os.path.dirname(engine.url.database) or ".", exist_ok=True)
    Base.metadata.create_all(engine)
    log.info("Created all tables", extra={"backend": engine.url.get_backend_name()})


def reset() -> None:
    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:
        os.makedirs(os.path.dirname(engine.url.database) or ".", exist_ok=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    log.info("Reset (dropped + created) all tables")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ DB CLI")
    parser.add_argument("command", choices=["reset", "create"])
    args = parser.parse_args()
    if args.command == "reset":
        reset()
    else:
        create_all()


if __name__ == "__main__":
    main()
