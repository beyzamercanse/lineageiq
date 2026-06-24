"""ML inference: load the persisted bundle and score incidents / reports."""

from __future__ import annotations

from dataclasses import dataclass

import joblib
import numpy as np

from app.ml.training import BUNDLE_PATH, ModelBundle


@dataclass
class RootCausePrediction:
    root_cause_code: str
    probability: float
    probabilities: dict[str, float]
    severity: str


class MLService:
    """Lazy-loaded ML inference over the trained bundle."""

    def __init__(self, bundle: ModelBundle):
        self.bundle = bundle

    @classmethod
    def load(cls, path=BUNDLE_PATH) -> MLService | None:
        if not path.exists():
            return None
        return cls(joblib.load(path))

    def predict_root_cause(self, features: list[float]) -> RootCausePrediction:
        x = np.array([features], dtype=float)
        clf = self.bundle.classifier
        proba = clf.predict_proba(x)[0]
        classes = list(clf.classes_)
        probabilities = {c: float(p) for c, p in zip(classes, proba)}
        best_idx = int(np.argmax(proba))
        severity = str(self.bundle.severity_model.predict(x)[0])
        return RootCausePrediction(
            root_cause_code=classes[best_idx],
            probability=float(proba[best_idx]),
            probabilities=probabilities,
            severity=severity,
        )

    def anomaly_score(self, report_features: list[float]) -> float:
        """Higher = more anomalous (sign-flipped Isolation Forest score)."""
        x = np.array([report_features], dtype=float)
        return float(-self.bundle.isolation_forest.score_samples(x)[0])

    def is_anomaly(self, report_features: list[float]) -> bool:
        x = np.array([report_features], dtype=float)
        return int(self.bundle.isolation_forest.predict(x)[0]) == -1
