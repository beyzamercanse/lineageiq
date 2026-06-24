"""Incident CLI.

    python -m app.incidents.cli generate [--per-type 8] [--small]
    python -m app.incidents.cli inject --incident-id <id>
    python -m app.incidents.cli inject --incident-type stale_fx_rate --first
    python -m app.incidents.cli restore [--small]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.taxonomy import IncidentType
from app.db.cli import create_all
from app.db.session import session_scope
from app.incidents.manifest import load_manifest
from app.incidents.restore import restore_clean_baseline
from app.incidents.service import generate_manifests, run_incident_pipeline
from app.models import Order
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset

log = get_logger(__name__)


def _config(small: bool) -> GeneratorConfig:
    return GeneratorConfig.small() if small else GeneratorConfig(seed=get_settings().random_seed)


def generate(per_type: int, small: bool) -> None:
    create_all()
    cfg = _config(small)
    with session_scope() as session:
        if (session.scalar(select(func.count()).select_from(Order)) or 0) == 0:
            print("No data found; seeding clean baseline first...")
            generate_clean_dataset(session, cfg)
        manifests = generate_manifests(session, seed=cfg.seed, per_type=per_type)
    print(f"Generated {len(manifests)} incident manifests in data/incident_manifests/")


def inject(incident_id: str | None, incident_type: str | None, first: bool, small: bool) -> None:
    if incident_id is None:
        if incident_type is None:
            print("Provide --incident-id or --incident-type", file=sys.stderr)
            sys.exit(2)
        # --first selects the first manifest of the type (index 0); default is the same.
        incident_id = f"{IncidentType(incident_type).value}-01"
    manifest = load_manifest(incident_id)
    cfg = _config(small)
    with session_scope() as session:
        incident = run_incident_pipeline(session, manifest, config=cfg)
        iid = incident.incident_id
        severity = incident.severity
        system = incident.primary_affected_system
    print(f"Injected '{manifest.manifest_id}' ({manifest.incident_type.value})")
    print(f"  -> incident {iid}  severity={severity}  system={system}")
    print(f"  root cause (ground truth): {manifest.root_cause_code.value}")


def restore(small: bool) -> None:
    create_all()
    cfg = _config(small)
    with session_scope() as session:
        counts = restore_clean_baseline(session, cfg)
    print(f"Restored clean baseline ({counts['orders']} orders).")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="LineageIQ incident CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate incident manifests")
    g.add_argument("--per-type", type=int, default=8)
    g.add_argument("--small", action="store_true")

    i = sub.add_parser("inject", help="Restore clean data, inject one incident, detect, create it")
    i.add_argument("--incident-id")
    i.add_argument("--incident-type")
    i.add_argument("--first", action="store_true")
    i.add_argument("--small", action="store_true")

    r = sub.add_parser("restore", help="Restore the clean baseline")
    r.add_argument("--small", action="store_true")

    args = parser.parse_args()
    if args.command == "generate":
        generate(args.per_type, args.small)
    elif args.command == "inject":
        inject(args.incident_id, args.incident_type, args.first, args.small)
    elif args.command == "restore":
        restore(args.small)


if __name__ == "__main__":
    main()
