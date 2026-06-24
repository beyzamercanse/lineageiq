"""Deterministic synthetic-data generator for AtlasCommerce.

Same seed => identical data. Money is Decimal; timestamps are UTC. The clean baseline produced
here satisfies every invariant asserted by ``validator.py``.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    AgentRun,
    Alert,
    CrmCustomer,
    Customer,
    CustomerLimit,
    DailyRevenueReport,
    Evidence,
    FxRate,
    HistoricalIncident,
    Incident,
    IncidentGroundTruth,
    Order,
    Payment,
    PipelineDefinition,
    PipelineRun,
    Refund,
    SchemaEvent,
    Shipment,
    StagingRecord,
    SystemLog,
)
from app.simulator.config import (
    CARRIERS,
    COUNTRY_CURRENCY,
    CUSTOMER_SEGMENTS,
    PAYMENT_PROVIDERS,
    PIPELINES,
    REFUND_REASONS,
    REGIONS,
    REPORTING_CURRENCY,
    GeneratorConfig,
)
from app.simulator.fx import build_fx_table, convert

log = get_logger(__name__)

CENTS = Decimal("0.01")

# Tables wiped (in FK-safe order, children first) before regeneration. Includes incident
# artifacts and staging/schema tables so a regenerate doubles as a full clean restore.
_WIPE_ORDER = [
    Evidence, AgentRun, IncidentGroundTruth, Alert, Incident,
    SchemaEvent, StagingRecord,
    SystemLog, PipelineRun, PipelineDefinition, DailyRevenueReport, Shipment, Refund,
    Payment, Order, CustomerLimit, Customer, CrmCustomer, FxRate, HistoricalIncident,
]


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2))).quantize(CENTS, rounding=ROUND_HALF_UP)


class DataGenerator:
    """Builds a referentially consistent clean baseline."""

    def __init__(self, config: GeneratorConfig):
        self.cfg = config
        self.rng = random.Random(config.seed)
        self.days: list[date] = [
            (config.start + timedelta(days=i)).date() for i in range(config.days)
        ]
        # FX must also cover refund/shipment dates that fall after the order window
        # (refunds occur up to ~10 days after payment). Extend with a buffer.
        self.fx_days: list[date] = [
            (config.start + timedelta(days=i)).date() for i in range(config.days + 20)
        ]
        self.fx_table: dict[tuple[date, str, str], Decimal] = {}

    # -- public ----------------------------------------------------------------
    def generate(self, session: Session) -> dict[str, int]:
        """Wipe and regenerate the full clean dataset. Returns row counts."""
        self._wipe(session)
        self.fx_table = build_fx_table(self.fx_days, self.rng)

        counts: dict[str, int] = {}
        crm = self._gen_crm_customers()
        customers = self._gen_customers(crm)
        limits = self._gen_limits(customers)
        fx_rows = self._fx_rows()
        orders, customers_by_id = self._gen_orders(customers)
        payments = self._gen_payments(orders)
        refunds = self._gen_refunds(payments, orders)
        shipments = self._gen_shipments(orders)
        pipelines = self._gen_pipeline_defs()
        runs = self._gen_pipeline_runs()
        logs = self._gen_logs(runs)
        reports = self._gen_reports(orders, payments, refunds, customers_by_id)
        historical = self._gen_historical_incidents()

        # Insert in FK-safe order.
        self._bulk(session, CrmCustomer, crm)
        self._bulk(session, Customer, customers)
        self._bulk(session, CustomerLimit, limits)
        self._bulk(session, FxRate, fx_rows)
        self._bulk(session, Order, orders)
        self._bulk(session, Payment, payments)
        self._bulk(session, Refund, refunds)
        self._bulk(session, Shipment, shipments)
        self._bulk(session, PipelineDefinition, pipelines)
        self._bulk(session, PipelineRun, runs)
        self._bulk(session, SystemLog, logs)
        self._bulk(session, DailyRevenueReport, reports)
        self._bulk(session, HistoricalIncident, historical)
        session.flush()

        counts = {
            "crm_customers": len(crm), "customers": len(customers),
            "customer_limits": len(limits), "fx_rates": len(fx_rows),
            "orders": len(orders), "payments": len(payments), "refunds": len(refunds),
            "shipments": len(shipments), "pipeline_definitions": len(pipelines),
            "pipeline_runs": len(runs), "system_logs": len(logs),
            "daily_revenue_report": len(reports), "historical_incidents": len(historical),
        }
        log.info("Generated clean dataset", extra={"counts": counts})
        return counts

    # -- helpers ---------------------------------------------------------------
    def _wipe(self, session: Session) -> None:
        for model in _WIPE_ORDER:
            session.execute(delete(model))
        session.flush()

    def _bulk(self, session: Session, model, rows: list[dict]) -> None:
        if rows:
            session.execute(insert(model), rows)

    def _dt(self, d: date, hour: int = 9, minute: int = 0) -> datetime:
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)

    # -- generators ------------------------------------------------------------
    def _gen_crm_customers(self) -> list[dict]:
        rows = []
        suffixes = ["Ltd", "GmbH", "SAS", "Inc", "KK"]
        for i in range(1, self.cfg.n_customers + 1):
            region = self.rng.choice(list(REGIONS))
            country = self.rng.choice(REGIONS[region]["countries"])
            suffix = self.rng.choice(suffixes)
            rows.append(
                {
                    "crm_customer_id": f"CRM-{i:06d}",
                    "external_customer_reference": f"EXT-{self.rng.randint(10**6, 10**7 - 1)}",
                    "legal_name": f"AtlasClient {i:04d} {suffix}",
                    "country": country,
                    "segment": self.rng.choice(CUSTOMER_SEGMENTS),
                    "updated_at": self._dt(self.days[0], 1),
                }
            )
        return rows

    def _gen_customers(self, crm: list[dict]) -> list[dict]:
        rows = []
        for i, crm_row in enumerate(crm, start=1):
            country = crm_row["country"]
            region = next(r for r, m in REGIONS.items() if country in m["countries"])
            rows.append(
                {
                    "customer_id": f"CUST-{i:06d}",
                    "legal_name": crm_row["legal_name"],
                    "country": country,
                    "region": region,
                    "base_currency": COUNTRY_CURRENCY[country],
                    "crm_customer_id": crm_row["crm_customer_id"],
                    "created_at": self._dt(self.days[0], 2),
                    "status": "active",
                }
            )
        return rows

    def _gen_limits(self, customers: list[dict]) -> list[dict]:
        rows = []
        for i, c in enumerate(customers, start=1):
            rows.append(
                {
                    "limit_id": f"LIM-{i:06d}",
                    "customer_id": c["customer_id"],
                    "currency": c["base_currency"],
                    "credit_limit": _money(self.rng.choice([50000, 100000, 250000, 500000])),
                    "effective_from": self._dt(self.days[0], 0),
                    "effective_to": None,
                    "updated_at": self._dt(self.days[0], 2),
                }
            )
        return rows

    def _fx_rows(self) -> list[dict]:
        rows = []
        for (d, src, tgt), rate in self.fx_table.items():
            rows.append(
                {
                    "rate_date": d,
                    "source_currency": src,
                    "target_currency": tgt,
                    "provider": "ecb_proxy",
                    "exchange_rate": rate,
                    "retrieved_at": self._dt(d, 0),
                }
            )
        return rows

    def _gen_orders(self, customers: list[dict]) -> tuple[list[dict], dict[str, dict]]:
        customers_by_id = {c["customer_id"]: c for c in customers}
        rows = []
        for i in range(1, self.cfg.n_orders + 1):
            cust = self.rng.choice(customers)
            d = self.rng.choice(self.days)
            hour = self.rng.randint(0, 23)
            minute = self.rng.randint(0, 59)
            currency = cust["base_currency"]
            gross = _money(self.rng.uniform(50, 50000))
            tax_rate = Decimal(REGIONS[cust["region"]]["tax_rate"])
            tax = (gross * tax_rate).quantize(CENTS, rounding=ROUND_HALF_UP)
            net = gross - tax
            cancelled = self.rng.random() < self.cfg.cancel_rate
            rows.append(
                {
                    "order_id": f"ORD-{i:06d}",
                    "customer_id": cust["customer_id"],
                    "order_timestamp": self._dt(d, hour, minute),
                    "order_currency": currency,
                    "gross_amount": gross,
                    "net_amount": net,
                    "tax_amount": tax,
                    "order_status": "cancelled" if cancelled else "completed",
                    "source_system": "Orders",
                    "updated_at": self._dt(d, hour, minute),
                }
            )
        return rows, customers_by_id

    def _gen_payments(self, orders: list[dict]) -> list[dict]:
        rows = []
        pay_i = 0
        for o in orders:
            if o["order_status"] == "cancelled":
                continue
            pay_i += 1
            r = self.rng.random()
            if r < self.cfg.failed_payment_rate:
                status = "failed"
            elif r < self.cfg.failed_payment_rate + self.cfg.pending_payment_rate:
                status = "pending"
            else:
                status = "successful"
            ts = o["order_timestamp"] + timedelta(hours=self.rng.randint(0, 6))
            rows.append(
                {
                    "payment_id": f"PAY-{pay_i:06d}",
                    "order_id": o["order_id"],
                    "customer_id": o["customer_id"],
                    "payment_timestamp": ts,
                    "payment_currency": o["order_currency"],
                    "payment_amount": o["gross_amount"],
                    "payment_status": status,
                    "payment_provider": self.rng.choice(PAYMENT_PROVIDERS),
                    "idempotency_key": f"IDEMP-{o['order_id']}",
                    "updated_at": ts,
                }
            )
        return rows

    def _gen_refunds(self, payments: list[dict], orders: list[dict]) -> list[dict]:
        rows = []
        ref_i = 0
        for p in payments:
            if p["payment_status"] != "successful":
                continue
            if self.rng.random() >= self.cfg.refund_rate:
                continue
            ref_i += 1
            full = self.rng.random() < 0.4
            if full:
                amount = p["payment_amount"]
            else:
                frac = Decimal(str(round(self.rng.uniform(0.1, 0.9), 2)))
                amount = (p["payment_amount"] * frac).quantize(CENTS, rounding=ROUND_HALF_UP)
            ts = p["payment_timestamp"] + timedelta(days=self.rng.randint(1, 10))
            rows.append(
                {
                    "refund_id": f"REF-{ref_i:06d}",
                    "payment_id": p["payment_id"],
                    "order_id": p["order_id"],
                    "customer_id": p["customer_id"],
                    "refund_timestamp": ts,
                    "refund_currency": p["payment_currency"],
                    "refund_amount": amount,
                    "refund_reason": self.rng.choice(REFUND_REASONS),
                    "refund_status": "completed",
                    "updated_at": ts,
                }
            )
        return rows

    def _gen_shipments(self, orders: list[dict]) -> list[dict]:
        rows = []
        shp_i = 0
        for o in orders:
            if o["order_status"] == "cancelled":
                continue
            if self.rng.random() >= self.cfg.shipment_rate:
                continue
            shp_i += 1
            # warehouse region from the order's customer region proxy via currency mapping
            region = self.rng.choice(list(REGIONS))
            shipped = o["order_timestamp"] + timedelta(days=self.rng.randint(0, 3))
            delivered = shipped + timedelta(days=self.rng.randint(1, 7))
            rows.append(
                {
                    "shipment_id": f"SHP-{shp_i:06d}",
                    "order_id": o["order_id"],
                    "warehouse_region": region,
                    "carrier": self.rng.choice(CARRIERS),
                    "shipment_status": "delivered",
                    "shipped_at": shipped,
                    "delivered_at": delivered,
                    "updated_at": delivered,
                }
            )
        return rows

    def _gen_pipeline_defs(self) -> list[dict]:
        rows = []
        for name, src, tgt, schedule, owner in PIPELINES:
            rows.append(
                {
                    "pipeline_id": f"PL-{name}",
                    "pipeline_name": name,
                    "source_system": src,
                    "target_system": tgt,
                    "schedule": schedule,
                    "owner": owner,
                    "active": True,
                }
            )
        return rows

    def _gen_pipeline_runs(self) -> list[dict]:
        rows = []
        for name, _src, _tgt, _sched, _owner in PIPELINES:
            for d in self.days:
                started = self._dt(d, 4)
                completed = started + timedelta(minutes=self.rng.randint(2, 25))
                rows.append(
                    {
                        "pipeline_run_id": f"PR-{name}-{d:%Y%m%d}",
                        "pipeline_id": f"PL-{name}",
                        "started_at": started,
                        "completed_at": completed,
                        "status": "completed",
                        "rows_read": self.rng.randint(100, 5000),
                        "rows_written": self.rng.randint(100, 5000),
                        "error_message": None,
                        "metadata": {"date": d.isoformat()},
                    }
                )
        return rows

    def _gen_logs(self, runs: list[dict]) -> list[dict]:
        rows = []
        log_i = 0
        for run in runs:
            for k in range(self.cfg.logs_per_run):
                log_i += 1
                rows.append(
                    {
                        "log_id": f"LOG-{log_i:07d}",
                        "timestamp": run["started_at"] + timedelta(seconds=k * 5),
                        "service": run["pipeline_id"],
                        "log_level": "INFO",
                        "message": (
                            f"{run['pipeline_id']} step {k} ok; "
                            f"read={run['rows_read']} written={run['rows_written']}"
                        ),
                        "correlation_id": run["pipeline_run_id"],
                        "pipeline_run_id": run["pipeline_run_id"],
                        "structured_metadata": {"step": k, "status": "ok"},
                    }
                )
        return rows

    def _gen_reports(
        self,
        orders: list[dict],
        payments: list[dict],
        refunds: list[dict],
        customers_by_id: dict[str, dict],
    ) -> list[dict]:
        gross: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
        order_count: dict[tuple[date, str], int] = defaultdict(int)
        refund_total: dict[tuple[date, str], Decimal] = defaultdict(lambda: Decimal("0"))
        pay_count: dict[tuple[date, str], int] = defaultdict(int)

        for o in orders:
            if o["order_status"] == "cancelled":
                continue
            region = customers_by_id[o["customer_id"]]["region"]
            d = o["order_timestamp"].date()
            usd = convert(
                o["gross_amount"], o["order_currency"], REPORTING_CURRENCY, d, self.fx_table
            )
            gross[(d, region)] += usd
            order_count[(d, region)] += 1

        for p in payments:
            if p["payment_status"] != "successful":
                continue
            region = customers_by_id[p["customer_id"]]["region"]
            d = p["payment_timestamp"].date()
            pay_count[(d, region)] += 1

        for r in refunds:
            region = customers_by_id[r["customer_id"]]["region"]
            d = r["refund_timestamp"].date()
            usd = convert(
                r["refund_amount"], r["refund_currency"], REPORTING_CURRENCY, d, self.fx_table
            )
            refund_total[(d, region)] += usd

        keys = set(gross) | set(refund_total) | set(pay_count)
        rows = []
        for d, region in sorted(keys):
            g = gross[(d, region)]
            rt = refund_total[(d, region)]
            rows.append(
                {
                    "report_date": d,
                    "region": region,
                    "reporting_currency": REPORTING_CURRENCY,
                    "gross_revenue": g,
                    "refund_total": rt,
                    "net_revenue": g - rt,
                    "order_count": order_count[(d, region)],
                    "payment_count": pay_count[(d, region)],
                    "generated_at": self._dt(d, 5),
                    "source_pipeline_run_id": f"PR-revenue_aggregation_pipeline-{d:%Y%m%d}",
                }
            )
        return rows

    def _gen_historical_incidents(self) -> list[dict]:
        templates = [
            ("stale_fx_rate", "STALE_FX_RATE", "EUR/USD rate not refreshed; USD revenue overstated",
             "FX API returned no new rate; pipeline reused prior day's rate",
             "Refresh FX data for affected date and regenerate daily_revenue_report",
             ["fx_rates", "daily_revenue_report"]),
            ("duplicate_transaction", "DUPLICATE_TRANSACTION", "Payment double-counted in revenue",
             "Retry without idempotency check created duplicate payment row",
             "Deduplicate by idempotency_key and rebuild affected aggregates",
             ["payments", "daily_revenue_report"]),
            ("missing_customer_mapping", "MISSING_CUSTOMER_MAPPING",
             "Orders unattributed to region",
             "CRM mapping pipeline dropped rows; customers.crm_customer_id null",
             "Backfill customer mapping from CRM and reprocess",
             ["customers", "crm_customers"]),
            ("delayed_pipeline", "DELAYED_PIPELINE", "Revenue report missing for a date",
             "Upstream ingest delayed beyond aggregation window",
             "Re-run aggregation after ingest completes",
             ["pipeline_runs", "daily_revenue_report"]),
            ("incorrect_aggregation", "INCORRECT_AGGREGATION", "Net revenue mismatch vs source",
             "Aggregation used wrong sign for refunds",
             "Fix aggregation logic and recompute",
             ["daily_revenue_report"]),
            ("upstream_api_failure", "UPSTREAM_API_FAILURE", "Burst of API errors before gap",
             "Payment provider API 5xx burst caused missing rows",
             "Replay failed windows once provider recovers",
             ["payments", "system_logs"]),
            ("null_contamination", "NULL_CONTAMINATION", "Null amounts broke totals",
             "Required field arrived null from source",
             "Quarantine null rows and reload",
             ["orders", "payments"]),
            ("timezone_conversion_error", "TIMEZONE_CONVERSION_ERROR", "Revenue shifted by a day",
             "Local timestamps treated as UTC",
             "Normalize to UTC and reaggregate",
             ["orders", "daily_revenue_report"]),
            ("partial_load", "PARTIAL_LOAD", "Row count far below expected",
             "File load truncated mid-stream",
             "Reload complete file and verify counts",
             ["orders", "pipeline_runs"]),
            ("schema_change", "SCHEMA_CONTRACT_CHANGE", "Field mapping broke ingestion",
             "Source renamed a field; staging mapping incompatible",
             "Update schema contract and reprocess staging",
             ["orders", "system_logs"]),
        ]
        rows = []
        for i in range(self.cfg.n_historical_incidents):
            t = templates[i % len(templates)]
            itype, code, title, root, remediation, systems = t
            occurred = self._dt(self.days[i % len(self.days)], 6) - timedelta(days=120)
            searchable = f"{title} {root} {remediation} {' '.join(systems)} {code}"
            rows.append(
                {
                    "historical_incident_id": f"HIST-{i + 1:04d}",
                    "title": title,
                    "incident_type": itype,
                    "symptoms": title,
                    "root_cause": root,
                    "affected_systems": systems,
                    "remediation": remediation,
                    "severity": self.rng.choice(["medium", "high"]),
                    "evidence_summary": f"Prior {code} incident with SQL + log + lineage evidence",
                    "searchable_text": searchable,
                    "occurred_at": occurred,
                }
            )
        return rows


def generate_clean_dataset(
    session: Session, config: GeneratorConfig | None = None
) -> dict[str, int]:
    """Convenience entrypoint."""
    return DataGenerator(config or GeneratorConfig()).generate(session)
