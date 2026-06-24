"""Reconciliation helpers shared by detectors.

Recomputes per (date, region) revenue aggregates from source rows using the *stored* FX rates, so
detectors can compare the published daily_revenue_report against ground-truth-from-source.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, DailyRevenueReport, FxRate, Order, Payment, Refund
from app.simulator.config import REPORTING_CURRENCY
from app.simulator.fx import convert


@dataclass
class Recomputed:
    gross: Decimal
    refund_total: Decimal
    order_count: int
    payment_count: int

    @property
    def net(self) -> Decimal:
        return self.gross - self.refund_total


def _fx_table(session: Session) -> dict[tuple[date, str, str], Decimal]:
    return {
        (r.rate_date, r.source_currency, r.target_currency): r.exchange_rate
        for r in session.execute(select(FxRate)).scalars()
    }


def recompute_from_source(session: Session) -> dict[tuple[date, str], Recomputed]:
    fx = _fx_table(session)
    region_by_customer = {
        c.customer_id: c.region for c in session.execute(select(Customer)).scalars()
    }
    gross: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
    refund_total: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
    order_count: dict[tuple[date, str], int] = defaultdict(int)
    pay_count: dict[tuple[date, str], int] = defaultdict(int)

    for o in session.execute(select(Order)).scalars():
        if o.order_status == "cancelled":
            continue
        region = region_by_customer.get(o.customer_id)
        if region is None:
            continue
        d = o.order_timestamp.date()
        gross[(d, region)] += convert(
            o.gross_amount, o.order_currency, REPORTING_CURRENCY, d, fx
        )
        order_count[(d, region)] += 1
    for p in session.execute(select(Payment)).scalars():
        if p.payment_status != "successful":
            continue
        region = region_by_customer.get(p.customer_id)
        if region is None:
            continue
        pay_count[(p.payment_timestamp.date(), region)] += 1
    for r in session.execute(select(Refund)).scalars():
        region = region_by_customer.get(r.customer_id)
        if region is None:
            continue
        d = r.refund_timestamp.date()
        refund_total[(d, region)] += convert(
            r.refund_amount, r.refund_currency, REPORTING_CURRENCY, d, fx
        )

    keys = set(gross) | set(refund_total) | set(pay_count)
    return {
        k: Recomputed(
            gross=gross[k], refund_total=refund_total[k],
            order_count=order_count[k], payment_count=pay_count[k],
        )
        for k in keys
    }


def load_reports(session: Session) -> dict[tuple[date, str], DailyRevenueReport]:
    return {
        (r.report_date, r.region): r
        for r in session.execute(select(DailyRevenueReport)).scalars()
    }
