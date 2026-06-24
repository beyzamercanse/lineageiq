"""Incident manifest: a reproducible plan + ground truth for one injected incident.

A manifest fully describes how to reproduce an incident (type, seed, target selectors) and what the
correct diagnosis is (root cause, affected systems/reports, expected evidence, escalation). Stored
as JSON under ``data/incident_manifests/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT
from app.core.taxonomy import IncidentType, RootCauseCode, Severity

MANIFEST_DIR = PROJECT_ROOT / "data" / "incident_manifests"


class IncidentManifest(BaseModel):
    """Reproducible plan + ground truth for a single incident."""

    manifest_id: str
    incident_type: IncidentType
    root_cause_code: RootCauseCode
    seed: int
    index: int
    title: str
    # Injector-specific, JSON-safe selectors (dates as ISO strings, ids as strings).
    params: dict[str, Any] = Field(default_factory=dict)
    changed_tables: list[str] = Field(default_factory=list)
    affected_pipeline: str | None = None
    expected_symptoms: list[str] = Field(default_factory=list)
    root_cause_description: str = ""
    expected_affected_systems: list[str] = Field(default_factory=list)
    expected_affected_reports: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    expected_remediation: str = ""
    severity: Severity = Severity.MEDIUM
    should_escalate: bool = False
    # Recorded after a real injection run (ids of changed records).
    changed_record_ids: list[str] = Field(default_factory=list)
    injected_at: str | None = None

    def path(self, base: Path | None = None) -> Path:
        return (base or MANIFEST_DIR) / f"{self.manifest_id}.json"

    def save(self, base: Path | None = None) -> Path:
        base = base or MANIFEST_DIR
        base.mkdir(parents=True, exist_ok=True)
        p = self.path(base)
        p.write_text(json.dumps(self.model_dump(mode="json"), indent=2))
        return p


def load_manifest(manifest_id: str, base: Path | None = None) -> IncidentManifest:
    p = (base or MANIFEST_DIR) / f"{manifest_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    return IncidentManifest.model_validate_json(p.read_text())


def load_all_manifests(base: Path | None = None) -> list[IncidentManifest]:
    base = base or MANIFEST_DIR
    if not base.exists():
        return []
    return [
        IncidentManifest.model_validate_json(p.read_text())
        for p in sorted(base.glob("*.json"))
    ]
