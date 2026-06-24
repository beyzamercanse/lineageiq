"""ML CLI.

    python -m app.ml.cli train [--per-type 8] [--small]
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.cli import create_all
from app.db.session import session_scope
from app.ml.training import train_models
from app.simulator.config import GeneratorConfig


def train(per_type: int, small: bool) -> None:
    seed = get_settings().random_seed
    cfg = GeneratorConfig.small() if small else GeneratorConfig(seed=seed)
    create_all()
    with session_scope() as session:
        bundle = train_models(session, seed=seed, per_type=per_type, config=cfg)
    print(f"Trained model bundle {bundle.version}")
    for k, v in bundle.metrics.items():
        print(f"  {k:28s} {v}")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ ML CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train", help="Train and persist ML models")
    t.add_argument("--per-type", type=int, default=8)
    t.add_argument("--small", action="store_true")
    args = parser.parse_args()
    if args.command == "train":
        train(args.per_type, args.small)


if __name__ == "__main__":
    main()
