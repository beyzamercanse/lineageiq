"""Simulator CLI.

    python -m app.simulator.cli seed [--small]
    python -m app.simulator.cli validate
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.cli import create_all
from app.db.session import session_scope
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset
from app.simulator.validator import validate_clean_baseline

log = get_logger(__name__)


def seed(small: bool = False) -> None:
    settings = get_settings()
    cfg = GeneratorConfig.small() if small else GeneratorConfig(seed=settings.random_seed)
    create_all()
    with session_scope() as session:
        counts = generate_clean_dataset(session, cfg)
    print("Seeded clean dataset:")
    for k, v in counts.items():
        print(f"  {k:24s} {v:>8d}")


def validate() -> int:
    with session_scope() as session:
        report = validate_clean_baseline(session)
    print("Clean-baseline validation:")
    for c in report.checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.name}  {c.detail}")
    if report.passed:
        print("All checks passed.")
        return 0
    print("VALIDATION FAILED.", file=sys.stderr)
    return 1


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ simulator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    seed_p = sub.add_parser("seed", help="Generate the clean dataset")
    seed_p.add_argument("--small", action="store_true", help="Use the small test config")
    sub.add_parser("validate", help="Validate the clean baseline")

    args = parser.parse_args()
    if args.command == "seed":
        seed(small=args.small)
    elif args.command == "validate":
        sys.exit(validate())


if __name__ == "__main__":
    main()
