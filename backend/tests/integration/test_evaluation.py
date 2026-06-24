from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.evaluation.runner import run_evaluation
from app.models import Base
from app.simulator.config import GeneratorConfig


@pytest.mark.integration
def test_evaluation_runs_all_categories_and_scores():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    cfg = GeneratorConfig.small()

    output = run_evaluation(s, per_type=1, config=cfg, persist=False)
    m = output.metrics

    # One incident per category evaluated.
    assert m["n_incidents"] == 10
    assert len(output.per_incident) == 10
    # Detector-derived diagnosis is correct for every category.
    assert m["root_cause_top1_accuracy"] == 1.0
    assert m["root_cause_top3_accuracy"] == 1.0
    assert m["baseline_top1_accuracy"] == 1.0
    # Metric block is well-formed.
    assert 0.0 <= m["classification_macro_f1"] <= 1.0
    assert "escalation_f1" in m
    assert "calibration" in m and "brier_score" in m["calibration"]
    assert m["mean_tool_calls"] > 0
    s.close()


@pytest.mark.integration
def test_evaluation_records_failures_not_skips():
    # Every per-incident result is recorded (no silent skipping).
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    output = run_evaluation(s, per_type=1, config=GeneratorConfig.small(), persist=False)
    manifest_ids = {r.manifest_id for r in output.per_incident}
    assert len(manifest_ids) == 10
    s.close()
