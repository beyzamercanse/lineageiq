"""Reproducible ML training.

Builds a labeled dataset by injecting each manifest into a fresh clean baseline and extracting the
deterministic detectors' signals as features. Trains:
  - IsolationForest (numeric anomaly scoring over daily report features)
  - a calibrated GradientBoosting classifier (root-cause code)
  - a GradientBoosting severity model
Persists artifacts + metrics + a model version (feature defs, seeds, metrics).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.metrics import f1_score
from sklearn.model_selection import cross_val_predict
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger
from app.detection.detectors import run_all_detectors
from app.incidents.restore import restore_clean_baseline
from app.incidents.service import generate_manifests, inject_manifest
from app.ml.features import (
    INCIDENT_FEATURE_NAMES,
    extract_incident_features,
    report_feature_matrix,
)
from app.simulator.config import GeneratorConfig

log = get_logger(__name__)

ARTIFACT_DIR = PROJECT_ROOT / "backend" / "app" / "ml" / "artifacts"
BUNDLE_PATH = ARTIFACT_DIR / "model_bundle.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"


@dataclass
class ModelBundle:
    version: str
    created_at: str
    seed: int
    feature_names: list[str]
    classifier: Any
    severity_model: Any
    isolation_forest: Any
    classes: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)


def build_training_dataset(
    session: Session, seed: int, per_type: int, config: GeneratorConfig
) -> tuple[list[list[float]], list[str], list[str]]:
    """Return (features, root_cause_labels, severity_labels)."""
    # Ensure a clean baseline exists so manifest planning can select real targets.
    restore_clean_baseline(session, config)
    session.flush()
    manifests = generate_manifests(session, seed=seed, per_type=per_type, save=False)
    x: list[list[float]] = []
    y_cause: list[str] = []
    y_sev: list[str] = []
    for m in manifests:
        restore_clean_baseline(session, config)
        session.flush()
        inject_manifest(session, m)
        session.flush()
        alerts = run_all_detectors(session)
        x.append(extract_incident_features(alerts))
        y_cause.append(m.root_cause_code.value)
        y_sev.append(m.severity.value)
    return x, y_cause, y_sev


def _cv_for(labels: list[str]) -> int:
    min_count = min(Counter(labels).values())
    return max(2, min(3, min_count))


def train_models(
    session: Session,
    *,
    seed: int = 20240601,
    per_type: int = 8,
    config: GeneratorConfig | None = None,
    persist: bool = True,
) -> ModelBundle:
    config = config or GeneratorConfig(seed=seed)
    x_list, y_cause, y_sev = build_training_dataset(session, seed, per_type, config)
    x = np.array(x_list, dtype=float)

    # Isolation Forest on a clean baseline's report features (numeric anomaly detection).
    restore_clean_baseline(session, config)
    session.flush()
    report_rows, _ = report_feature_matrix(session)
    iso = IsolationForest(random_state=seed, contamination="auto")
    iso.fit(np.array(report_rows, dtype=float))

    classes = sorted(set(y_cause))
    cv = _cv_for(y_cause)

    base = GradientBoostingClassifier(random_state=seed)
    classifier = CalibratedClassifierCV(base, cv=cv, method="sigmoid")
    classifier.fit(x, y_cause)

    severity_model = GradientBoostingClassifier(random_state=seed)
    severity_model.fit(x, y_sev)

    # Cross-validated honest metrics for the root-cause classifier.
    cause_pred = cross_val_predict(
        GradientBoostingClassifier(random_state=seed), x, y_cause, cv=cv
    )
    sev_pred = cross_val_predict(
        GradientBoostingClassifier(random_state=seed), x, y_sev, cv=_cv_for(y_sev)
    )
    metrics = {
        "n_samples": len(y_cause),
        "n_classes": len(classes),
        "root_cause_cv_accuracy": float((cause_pred == np.array(y_cause)).mean()),
        "root_cause_cv_macro_f1": float(f1_score(y_cause, cause_pred, average="macro")),
        "severity_cv_accuracy": float((sev_pred == np.array(y_sev)).mean()),
        "severity_cv_macro_f1": float(f1_score(y_sev, sev_pred, average="macro")),
        "cv_folds": cv,
    }

    bundle = ModelBundle(
        version=f"ml-{datetime.now(timezone.utc):%Y%m%d%H%M%S}",
        created_at=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        feature_names=INCIDENT_FEATURE_NAMES,
        classifier=classifier,
        severity_model=severity_model,
        isolation_forest=iso,
        classes=classes,
        metrics=metrics,
    )

    if persist:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, BUNDLE_PATH)
        METRICS_PATH.write_text(json.dumps({"version": bundle.version, **metrics}, indent=2))
        log.info("Persisted model bundle", extra={"version": bundle.version, "metrics": metrics})

    # Leave a clean baseline behind.
    restore_clean_baseline(session, config)
    session.flush()
    return bundle
