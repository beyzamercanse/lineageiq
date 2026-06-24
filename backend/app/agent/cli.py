"""Agent CLI.

    python -m app.agent.cli investigate --incident-id <id>
"""

from __future__ import annotations

import argparse
import json

from app.agent.orchestrator import investigate_incident
from app.core.logging import configure_logging
from app.db.session import session_scope


def investigate(incident_id: str, as_json: bool) -> None:
    with session_scope() as session:
        report = investigate_incident(session, incident_id)
        payload = report.model_dump(mode="json")

    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Investigation report for {report.incident_id}")
    print(f"  summary: {report.summary}")
    print("  ranked root causes:")
    for c in report.root_cause_candidates:
        print(f"    {c.rank}. {c.root_cause_code}  confidence={c.confidence:.2f}  "
              f"evidence={len(c.supporting_evidence_ids)}")
    print(f"  impacted systems: {report.impacted_systems}")
    print(f"  impacted reports: {report.impacted_reports}")
    print(f"  requires human review: {report.requires_human_review} ({report.human_review_reason})")
    print("  remediation (requires approval):")
    for r in report.remediation_recommendations:
        print(f"    - {r.action} [{r.target_system}, risk={r.risk}]")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("investigate", help="Investigate an incident")
    inv.add_argument("--incident-id", required=True)
    inv.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "investigate":
        investigate(args.incident_id, args.json)


if __name__ == "__main__":
    main()
