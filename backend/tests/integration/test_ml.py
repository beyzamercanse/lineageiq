from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.taxonomy import IncidentType, RootCauseCode
from app.detection.detectors import run_all_detectors
from app.incidents.injectors import get_injector
from app.ml.features import extract_incident_features
from app.ml.historical import HistoricalIndex
from app.ml.inference import MLService
from app.ml.training import train_models
from app.models import Base
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset


def _seeded() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    generate_clean_dataset(s, GeneratorConfig.small())
    s.flush()
    return s


@pytest.mark.integration
def test_historical_search_finds_relevant_incident():
    s = _seeded()
    index = HistoricalIndex(n_clusters=4).fit(s)
    matches = index.search("EUR USD exchange rate not refreshed stale revenue", k=3)
    assert matches
    assert matches[0].incident_type == "stale_fx_rate"
    s.close()


@pytest.mark.integration
def test_training_persists_metrics_and_predicts_root_cause():
    s = _seeded()
    cfg = GeneratorConfig.small()
    bundle = train_models(s, seed=cfg.seed, per_type=2, config=cfg, persist=False)
    assert bundle.metrics["n_samples"] == 20
    assert 0.0 <= bundle.metrics["root_cause_cv_accuracy"] <= 1.0

    service = MLService(bundle)

    # Build a stale-FX feature vector from real detection and check the classifier.
    inj = get_injector(IncidentType.STALE_FX_RATE)
    m = inj.plan(s, seed=cfg.seed, index=0)
    inj.apply(s, m)
    s.flush()
    feats = extract_incident_features(run_all_detectors(s))
    pred = service.predict_root_cause(feats)
    assert pred.root_cause_code == RootCauseCode.STALE_FX_RATE.value
    assert 0.0 <= pred.probability <= 1.0
    s.close()


@pytest.mark.integration
def test_isolation_forest_scores_reports():
    s = _seeded()
    cfg = GeneratorConfig.small()
    bundle = train_models(s, seed=cfg.seed, per_type=2, config=cfg, persist=False)
    service = MLService(bundle)
    score = service.anomaly_score([1_000_000.0, 0.0, 1_000_000.0, 5000, 5000])
    assert isinstance(score, float)
    s.close()
