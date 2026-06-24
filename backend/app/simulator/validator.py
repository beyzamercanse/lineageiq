"""Clean-baseline validation: asserts the generated dataset is internally consistent.

These are exactly the invariants that incident injectors (Phase 2) violate. Returns a structured
report; ``make validate-data`` exits non-zero if any check fails.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CrmCustomer,
    Customer,
    DailyRevenueReport,
    FxRate,
    Order,
    Payment,
    Refund,
    Shipment,
)
from app.simulator.config import REPORTING_CURRENCY
from app.simulator.fx import convert


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))


def _fx_table_from_db(session: Session) -> dict[tuple[date, str, str], Decimal]:
    table: dict[tuple[date, str, str], Decimal] = {}
    for row in session.execute(select(FxRate)).scalars():
        table[(row.rate_date, row.source_currency, row.target_currency)] = row.exchange_rate
    return table


def validate_clean_baseline(session: Session) -> ValidationReport:
    report = ValidationReport()

    # 1. Non-empty.
    n_customers = session.scalar(select(func.count()).select_from(Customer)) or 0
    n_orders = session.scalar(select(func.count()).select_from(Order)) or 0
    report.add("dataset_non_empty", n_customers > 0 and n_orders > 0,
               f"customers={n_customers} orders={n_orders}")

    # 2. Referential integrity: orders.customer_id -> customers.
    orphan_orders = session.scalar(
        select(func.count()).select_from(Order)
        .where(~Order.customer_id.in_(select(Customer.customer_id)))
    ) or 0
    report.add("orders_reference_customers", orphan_orders == 0, f"orphans={orphan_orders}")

    # 3. customers.crm_customer_id -> crm_customers (clean: all mapped).
    unmapped = session.scalar(
        select(func.count()).select_from(Customer)
        .where(
            (Customer.crm_customer_id.is_(None))
            | (~Customer.crm_customer_id.in_(select(CrmCustomer.crm_customer_id)))
        )
    ) or 0
    report.add("customers_mapped_to_crm", unmapped == 0, f"unmapped={unmapped}")

    # 4. payments.order_id -> orders and customer matches.
    bad_payment_order = session.scalar(
        select(func.count()).select_from(Payment)
        .where(~Payment.order_id.in_(select(Order.order_id)))
    ) or 0
    report.add("payments_reference_orders", bad_payment_order == 0, f"orphans={bad_payment_order}")

    # 5. refunds.payment_id -> payments.
    bad_refund = session.scalar(
        select(func.count()).select_from(Refund)
        .where(~Refund.payment_id.in_(select(Payment.payment_id)))
    ) or 0
    report.add("refunds_reference_payments", bad_refund == 0, f"orphans={bad_refund}")

    # 6. shipments.order_id -> orders.
    bad_ship = session.scalar(
        select(func.count()).select_from(Shipment)
        .where(~Shipment.order_id.in_(select(Order.order_id)))
    ) or 0
    report.add("shipments_reference_orders", bad_ship == 0, f"orphans={bad_ship}")

    # 7. order net + tax == gross.
    bad_amounts = 0
    for o in session.execute(select(Order)).scalars():
        if o.net_amount + o.tax_amount != o.gross_amount:
            bad_amounts += 1
    report.add("order_amounts_balance", bad_amounts == 0, f"mismatches={bad_amounts}")

    # 8. refund_amount <= payment_amount.
    pay_amounts = {
        p.payment_id: p.payment_amount
        for p in session.execute(select(Payment)).scalars()
    }
    over_refunds = 0
    for r in session.execute(select(Refund)).scalars():
        if r.payment_id in pay_amounts and r.refund_amount > pay_amounts[r.payment_id]:
            over_refunds += 1
    report.add("refunds_within_payment", over_refunds == 0, f"over={over_refunds}")

    # 9. No duplicate idempotency keys.
    dup_idem = session.execute(
        select(Payment.idempotency_key, func.count())
        .group_by(Payment.idempotency_key)
        .having(func.count() > 1)
    ).all()
    report.add("no_duplicate_idempotency_keys", len(dup_idem) == 0, f"dups={len(dup_idem)}")

    # 10. FX coverage: every currency used by orders has a rate for each order date.
    fx_table = _fx_table_from_db(session)
    missing_fx = 0
    order_cur_dates = session.execute(
        select(Order.order_currency, func.date(Order.order_timestamp)).distinct()
    ).all()
    for currency, d in order_cur_dates:
        dd = d if isinstance(d, date) else date.fromisoformat(str(d))
        if currency != REPORTING_CURRENCY and (dd, currency, REPORTING_CURRENCY) not in fx_table:
            missing_fx += 1
    report.add("fx_coverage_complete", missing_fx == 0, f"missing={missing_fx}")

    # 11. Revenue report reconciles to source data (exact Decimal).
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
        region = region_by_customer[o.customer_id]
        d = o.order_timestamp.date()
        gross[(d, region)] += convert(
            o.gross_amount, o.order_currency, REPORTING_CURRENCY, d, fx_table
        )
        order_count[(d, region)] += 1
    for p in session.execute(select(Payment)).scalars():
        if p.payment_status != "successful":
            continue
        pay_count[(p.payment_timestamp.date(), region_by_customer[p.customer_id])] += 1
    for r in session.execute(select(Refund)).scalars():
        region = region_by_customer[r.customer_id]
        d = r.refund_timestamp.date()
        refund_total[(d, region)] += convert(
            r.refund_amount, r.refund_currency, REPORTING_CURRENCY, d, fx_table
        )

    mismatches = 0
    n_reports = 0
    for rep in session.execute(select(DailyRevenueReport)).scalars():
        n_reports += 1
        key = (rep.report_date, rep.region)
        if (
            rep.gross_revenue != gross[key]
            or rep.refund_total != refund_total[key]
            or rep.net_revenue != gross[key] - refund_total[key]
            or rep.order_count != order_count[key]
            or rep.payment_count != pay_count[key]
        ):
            mismatches += 1
    report.add("revenue_report_reconciles", mismatches == 0,
               f"reports={n_reports} mismatches={mismatches}")

    return report
