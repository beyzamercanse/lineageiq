from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.taxonomy import ALL_INCIDENT_TYPES, root_cause_for
from app.detection.detectors import run_all_detectors
from app.incidents.injectors import get_injector
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


@pytest.mark.unit
def test_clean_baseline_raises_no_alerts():
    s = _seeded()
    alerts = run_all_detectors(s)
    assert alerts == [], f"unexpected alerts on clean data: {[a.detector_name for a in alerts]}"
    s.close()


@pytest.mark.unit
@pytest.mark.parametrize("incident_type", ALL_INCIDENT_TYPES, ids=lambda t: t.value)
def test_each_category_triggers_its_detector(incident_type):
    s = _seeded()
    injector = get_injector(incident_type)
    manifest = injector.plan(s, seed=GeneratorConfig.small().seed, index=0)
    injector.apply(s, manifest)
    s.flush()

    alerts = run_all_detectors(s)
    expected = root_cause_for(incident_type)
    suspected = {a.suspected_root_cause for a in alerts}
    assert expected in suspected, (
        f"{incident_type.value}: expected detector for {expected.value}, "
        f"got {[c.value for c in suspected]}"
    )
    s.close()
