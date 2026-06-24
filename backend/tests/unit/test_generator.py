from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Order, Payment
from app.simulator.config import GeneratorConfig
from app.simulator.generator import generate_clean_dataset


def _fresh_session() -> Session:
    engine = create_engine("sqlite://")  # in-memory, isolated per call
    Base.metadata.create_all(engine)
    return Session(engine)


def _order_fingerprint(session: Session) -> list[tuple]:
    rows = session.execute(
        select(Order.order_id, Order.customer_id, Order.gross_amount, Order.order_currency)
        .order_by(Order.order_id)
    ).all()
    return [(r[0], r[1], str(r[2]), r[3]) for r in rows]


@pytest.mark.unit
def test_generates_expected_volumes():
    s = _fresh_session()
    counts = generate_clean_dataset(s, GeneratorConfig.small())
    assert counts["customers"] == 40
    assert counts["orders"] == 600
    assert counts["payments"] > 0
    assert counts["fx_rates"] > 0
    assert counts["daily_revenue_report"] > 0
    assert counts["historical_incidents"] == 6
    s.close()


@pytest.mark.unit
def test_money_is_decimal_and_balances():
    s = _fresh_session()
    generate_clean_dataset(s, GeneratorConfig.small())
    for o in s.execute(select(Order)).scalars():
        assert isinstance(o.gross_amount, Decimal)
        assert o.net_amount + o.tax_amount == o.gross_amount
    s.close()


@pytest.mark.unit
def test_deterministic_same_seed_same_data():
    s1 = _fresh_session()
    s2 = _fresh_session()
    generate_clean_dataset(s1, GeneratorConfig.small())
    generate_clean_dataset(s2, GeneratorConfig.small())
    assert _order_fingerprint(s1) == _order_fingerprint(s2)
    s1.close()
    s2.close()


@pytest.mark.unit
def test_different_seed_differs():
    s1 = _fresh_session()
    s2 = _fresh_session()
    generate_clean_dataset(s1, GeneratorConfig(seed=1, n_customers=40, n_orders=600, days=20,
                                               n_historical_incidents=6))
    generate_clean_dataset(s2, GeneratorConfig(seed=2, n_customers=40, n_orders=600, days=20,
                                               n_historical_incidents=6))
    assert _order_fingerprint(s1) != _order_fingerprint(s2)
    s1.close()
    s2.close()


@pytest.mark.unit
def test_one_payment_per_noncancelled_order():
    s = _fresh_session()
    generate_clean_dataset(s, GeneratorConfig.small())
    orders = {o.order_id: o for o in s.execute(select(Order)).scalars()}
    payments = s.execute(select(Payment)).scalars().all()
    non_cancelled = [o for o in orders.values() if o.order_status != "cancelled"]
    assert len(payments) == len(non_cancelled)
    s.close()
