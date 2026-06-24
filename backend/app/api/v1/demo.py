"""Demo-control API: reset, seed, inject, run detection."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.cli import reset as reset_db
from app.db.session import session_scope
from app.detection.runner import run_and_create_incidents
from app.incidents.manifest import load_all_manifests, load_manifest
from app.incidents.service import run_incident_pipeline
from app.schemas.incident import IncidentSummary
from app.services.incident_query import _summary, list_incidents
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset

router = APIRouter(prefix="/demo", tags=["demo"])


def _config() -> GeneratorConfig:
    return GeneratorConfig(seed=get_settings().random_seed)


@router.post("/reset")
def reset() -> dict:
    reset_db()
    return {"status": "reset"}


@router.post("/seed")
def seed() -> dict:
    with session_scope() as session:
        counts = generate_clean_dataset(session, _config())
    return {"status": "seeded", "counts": counts}


@router.get("/manifests")
def manifests() -> list[dict]:
    return [
        {"manifest_id": m.manifest_id, "incident_type": m.incident_type.value,
         "title": m.title, "severity": m.severity.value}
        for m in load_all_manifests()
    ]


@router.post("/inject/{manifest_id}", response_model=IncidentSummary)
def inject(manifest_id: str) -> IncidentSummary:
    try:
        manifest = load_manifest(manifest_id)
    except FileNotFoundError as exc:
        raise NotFoundError(f"Manifest not found: {manifest_id}") from exc
    with session_scope() as session:
        incident = run_incident_pipeline(session, manifest, config=_config())
        return _summary(session, incident)


@router.post("/run-detection", response_model=list[IncidentSummary])
def run_detection() -> list[IncidentSummary]:
    with session_scope() as session:
        run_and_create_incidents(session)
    with session_scope() as session:
        return list_incidents(session)
