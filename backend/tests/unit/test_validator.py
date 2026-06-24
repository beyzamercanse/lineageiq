from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset
from app.simulator.validator import validate_clean_baseline


def _seeded_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    generate_clean_dataset(s, GeneratorConfig.small())
    return s


@pytest.mark.unit
def test_clean_baseline_passes_all_checks():
    s = _seeded_session()
    report = validate_clean_baseline(s)
    failed = [c for c in report.checks if not c.passed]
    assert report.passed, f"failed checks: {[(c.name, c.detail) for c in failed]}"
    s.close()


@pytest.mark.unit
def test_validator_detects_corruption():
    from app.models import Order

    s = _seeded_session()
    # Break an order's amount balance.
    o = s.execute(__import__("sqlalchemy").select(Order)).scalars().first()
    o.tax_amount = o.tax_amount + 1
    s.flush()
    report = validate_clean_baseline(s)
    assert not report.passed
    assert any(c.name == "order_amounts_balance" and not c.passed for c in report.checks)
    s.close()
