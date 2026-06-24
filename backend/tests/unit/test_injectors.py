from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import ALL_INCIDENT_TYPES, root_cause_for
from app.incidents.injectors import get_injector
from app.models import Base, Customer, Order, Payment
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
@pytest.mark.parametrize("incident_type", ALL_INCIDENT_TYPES, ids=lambda t: t.value)
def test_plan_is_deterministic(incident_type):
    s1, s2 = _seeded(), _seeded()
    seed = GeneratorConfig.small().seed
    m1 = get_injector(incident_type).plan(s1, seed=seed, index=0)
    m2 = get_injector(incident_type).plan(s2, seed=seed, index=0)
    assert m1.params == m2.params
    assert m1.root_cause_code == root_cause_for(incident_type)
    s1.close()
    s2.close()


@pytest.mark.unit
@pytest.mark.parametrize("incident_type", ALL_INCIDENT_TYPES, ids=lambda t: t.value)
def test_apply_changes_something_and_is_reproducible(incident_type):
    s1, s2 = _seeded(), _seeded()
    seed = GeneratorConfig.small().seed
    inj = get_injector(incident_type)
    m1 = inj.plan(s1, seed=seed, index=0)
    m2 = inj.plan(s2, seed=seed, index=0)
    changed1 = inj.apply(s1, m1)
    changed2 = inj.apply(s2, m2)
    assert changed1, f"{incident_type.value} changed nothing"
    assert sorted(changed1) == sorted(changed2)
    s1.close()
    s2.close()


@pytest.mark.unit
def test_duplicate_injector_adds_one_payment_only():
    s = _seeded()
    before = s.scalar(select(func.count()).select_from(Payment))
    cust_before = s.scalar(select(func.count()).select_from(Customer))
    inj = get_injector(ALL_INCIDENT_TYPES[0])  # duplicate_transaction is first
    m = inj.plan(s, seed=GeneratorConfig.small().seed, index=0)
    inj.apply(s, m)
    s.flush()
    assert s.scalar(select(func.count()).select_from(Payment)) == before + 1
    assert s.scalar(select(func.count()).select_from(Customer)) == cust_before
    s.close()


@pytest.mark.unit
def test_missing_mapping_only_nulls_mapping_keeps_counts():
    from app.core.taxonomy import IncidentType

    s = _seeded()
    orders_before = s.scalar(select(func.count()).select_from(Order))
    inj = get_injector(IncidentType.MISSING_CUSTOMER_MAPPING)
    m = inj.plan(s, seed=GeneratorConfig.small().seed, index=0)
    inj.apply(s, m)
    s.flush()
    # Customer rows unchanged in count; only the mapping field nulled.
    nulls = s.scalar(
        select(func.count()).select_from(Customer).where(Customer.crm_customer_id.is_(None))
    )
    assert nulls == len(m.params["customer_ids"])
    assert s.scalar(select(func.count()).select_from(Order)) == orders_before
    s.close()
