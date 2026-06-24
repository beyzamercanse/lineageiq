"""Detection CLI.

    python -m app.detection.cli run     # run controls, create incidents grouped by root cause
"""

from __future__ import annotations

import argparse

from app.core.logging import configure_logging
from app.db.session import session_scope
from app.detection.runner import run_and_create_incidents


def run() -> None:
    with session_scope() as session:
        incidents = run_and_create_incidents(session)
        summary = [(i.incident_id, i.primary_affected_system, i.severity) for i in incidents]
    if not summary:
        print("No anomalies detected.")
        return
    print(f"Detected {len(summary)} incident(s):")
    for iid, system, severity in summary:
        print(f"  {iid}  system={system}  severity={severity}")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ detection CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run detection and create incidents")
    args = parser.parse_args()
    if args.command == "run":
        run()


if __name__ == "__main__":
    main()
