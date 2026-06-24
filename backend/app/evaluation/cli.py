"""Evaluation CLI.

    python -m app.evaluation.cli run [--per-type 8] [--small]
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.cli import create_all
from app.db.session import session_scope
from app.evaluation.runner import run_evaluation
from app.simulator.config import GeneratorConfig


def run(per_type: int, small: bool) -> None:
    seed = get_settings().random_seed
    cfg = GeneratorConfig.small() if small else GeneratorConfig(seed=seed)
    create_all()
    with session_scope() as session:
        output = run_evaluation(session, per_type=per_type, config=cfg)
    m = output.metrics
    print(f"Evaluated {m['n_incidents']} incidents")
    print(f"  root-cause top-1 accuracy : {m['root_cause_top1_accuracy']:.3f}")
    print(f"  root-cause top-3 accuracy : {m['root_cause_top3_accuracy']:.3f}")
    print(f"  classification macro-F1   : {m['classification_macro_f1']:.3f}")
    print(f"  unsupported (report-level): {m['unsupported_diagnosis_rate_report_level']:.3f}")
    print(f"  escalation F1             : {m['escalation_f1']:.3f}")
    print(f"  mean latency (s)          : {m['mean_latency_seconds']:.3f}")
    print("  report: data/evaluation/latest_report.md")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ evaluation CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="Run the evaluation suite")
    r.add_argument("--per-type", type=int, default=8)
    r.add_argument("--small", action="store_true")
    args = parser.parse_args()
    if args.command == "run":
        run(args.per_type, args.small)


if __name__ == "__main__":
    main()
