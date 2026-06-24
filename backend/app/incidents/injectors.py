"""Ten deterministic incident injectors.

Each injector can ``plan`` an incident (select targets from the clean baseline and emit a manifest
with full ground truth) and ``apply`` it (perform the controlled mutation in the manifest).

Design rules:
- Deterministic: targets derive from a stable seed (cross-process stable, not Python ``hash``).
- Recoverable: schema-change is simulated via metadata/staging/logs, never real DDL.
- Isolated: an injector changes only the records named in its manifest.
"""

from __future__ import annotations

import hashlib
import random
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import IncidentType, RootCauseCode, Severity, root_cause_for
from app.detection.severity import compute_severity
from app.incidents.manifest import IncidentManifest
from app.models import (
    Customer,
    DailyRevenueReport,
    FxRate,
    Order,
    Payment,
    Refund,
    SchemaEvent,
    Shipment,
    StagingRecord,
    SystemLog,
)


def stable_seed(*parts: object) -> int:
    """Cross-process-stable integer seed from arbitrary parts."""
    digest = hashlib.sha256("::".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _order_dates(session: Session) -> list[date]:
    rows = session.execute(
        select(func.date(Order.order_timestamp)).distinct()
    ).all()
    return sorted({_as_date(r[0]) for r in rows})


def _utc(d: date, hour: int = 10) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


class Injector(ABC):
    """Base class for incident injectors."""

    incident_type: IncidentType

    @property
    def root_cause_code(self) -> RootCauseCode:
        return root_cause_for(self.incident_type)

    def manifest_id(self, index: int) -> str:
        return f"{self.incident_type.value}-{index + 1:02d}"

    def rng(self, seed: int, index: int) -> random.Random:
        return random.Random(stable_seed(seed, self.incident_type.value, index))

    @abstractmethod
    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        """Select targets from clean data and return a manifest (no mutation)."""

    @abstractmethod
    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        """Apply the mutation described by the manifest; return changed record ids."""

    # Shared manifest builder.
    def _manifest(
        self,
        *,
        index: int,
        seed: int,
        title: str,
        params: dict,
        changed_tables: list[str],
        affected_pipeline: str | None,
        expected_symptoms: list[str],
        root_cause_description: str,
        expected_affected_systems: list[str],
        expected_affected_reports: list[str],
        expected_evidence: list[str],
        expected_remediation: str,
        severity: Severity,
    ) -> IncidentManifest:
        return IncidentManifest(
            manifest_id=self.manifest_id(index),
            incident_type=self.incident_type,
            root_cause_code=self.root_cause_code,
            seed=seed,
            index=index,
            title=title,
            params=params,
            changed_tables=changed_tables,
            affected_pipeline=affected_pipeline,
            expected_symptoms=expected_symptoms,
            root_cause_description=root_cause_description,
            expected_affected_systems=expected_affected_systems,
            expected_affected_reports=expected_affected_reports,
            expected_evidence=expected_evidence,
            expected_remediation=expected_remediation,
            should_escalate=severity in (Severity.HIGH, Severity.CRITICAL),
        )


# --------------------------------------------------------------------------- #
# 1. Duplicate transaction
# --------------------------------------------------------------------------- #
class DuplicateTransactionInjector(Injector):
    incident_type = IncidentType.DUPLICATE_TRANSACTION

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        pay_ids = list(session.execute(
            select(Payment.payment_id).where(Payment.payment_status == "successful")
        ).scalars())
        target = rng.choice(sorted(pay_ids))
        target_payment = session.get(Payment, target)
        assert target_payment is not None
        amount = target_payment.payment_amount
        severity = compute_severity(
            affected_records=1, monetary_exposure=amount, downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Duplicate payment double-counted in revenue",
            params={"payment_id": target},
            changed_tables=["payments", "system_logs"],
            affected_pipeline="payment_reconciliation_pipeline",
            expected_symptoms=[
                "Duplicate idempotency_key in payments",
                "Reported revenue higher than reconciled source",
            ],
            root_cause_description=(
                "A payment retry without idempotency enforcement created a duplicate payment row, "
                "double-counting the amount in revenue."
            ),
            expected_affected_systems=["Payments", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:duplicate_idempotency_key", "log:payment_retry"],
            expected_remediation=(
                "Deduplicate payments by idempotency_key and rebuild affected revenue aggregates."
            ),
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        orig = session.get(Payment, manifest.params["payment_id"])
        assert orig is not None
        dup_id = f"{orig.payment_id}-DUP"
        dup = Payment(
            payment_id=dup_id,
            order_id=orig.order_id,
            customer_id=orig.customer_id,
            payment_timestamp=orig.payment_timestamp + timedelta(minutes=2),
            payment_currency=orig.payment_currency,
            payment_amount=orig.payment_amount,
            payment_status="successful",
            payment_provider=orig.payment_provider,
            idempotency_key=orig.idempotency_key,  # same key => duplicate
            updated_at=orig.payment_timestamp + timedelta(minutes=2),
        )
        session.add(dup)
        session.add(SystemLog(
            log_id=f"LOG-INC-{dup_id}",
            timestamp=orig.payment_timestamp + timedelta(minutes=2),
            service="PL-payment_reconciliation_pipeline",
            log_level="WARN",
            message=f"Retry processed for idempotency_key={orig.idempotency_key} (no dedupe)",
            correlation_id=f"retry-{orig.payment_id}",
            pipeline_run_id=None,
            structured_metadata={"idempotency_key": orig.idempotency_key},
        ))
        return [dup_id]


# --------------------------------------------------------------------------- #
# 2. Stale FX rate
# --------------------------------------------------------------------------- #
class StaleFxRateInjector(Injector):
    incident_type = IncidentType.STALE_FX_RATE

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        dates = _order_dates(session)
        target_date = rng.choice(dates[5:-5])
        currency = rng.choice(["EUR", "GBP", "JPY", "TRY"])
        severity = compute_severity(
            affected_records=50, monetary_exposure=Decimal("250000"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title=f"Stale {currency}/USD rate overstates revenue",
            params={"date": target_date.isoformat(), "currency": currency},
            changed_tables=["fx_rates", "pipeline_runs", "system_logs"],
            affected_pipeline="fx_rate_pipeline",
            expected_symptoms=[
                f"{currency}/USD rate identical to previous day (no drift)",
                "daily_revenue_report does not reconcile to source",
            ],
            root_cause_description=(
                f"The FX pipeline failed to fetch a fresh {currency}/USD rate and reused the "
                "previous day's rate, so converted USD revenue deviates from the correct value."
            ),
            expected_affected_systems=["ForeignExchange", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=[
                "sql:fx_rate_compare", "pipeline:fx_rate_pipeline", "log:stale_rate",
            ],
            expected_remediation=(
                "Refresh FX data for the affected date and regenerate affected revenue reports."
            ),
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        currency = manifest.params["currency"]
        prev = d - timedelta(days=1)
        prev_rate = session.execute(
            select(FxRate).where(
                FxRate.rate_date == prev,
                FxRate.source_currency == currency,
                FxRate.target_currency == "USD",
            )
        ).scalar_one()
        cur = session.execute(
            select(FxRate).where(
                FxRate.rate_date == d,
                FxRate.source_currency == currency,
                FxRate.target_currency == "USD",
            )
        ).scalar_one()
        cur.exchange_rate = prev_rate.exchange_rate  # stale: reuse prior day
        cur.retrieved_at = _utc(d, 0)
        session.add(SystemLog(
            log_id=f"LOG-INC-stalefx-{d.isoformat()}-{currency}",
            timestamp=_utc(d, 0),
            service="PL-fx_rate_pipeline",
            log_level="WARN",
            message=f"FX provider returned no new {currency}/USD rate; reusing {prev.isoformat()}",
            correlation_id=f"fx-{d.isoformat()}",
            pipeline_run_id=f"PR-fx_rate_pipeline-{d:%Y%m%d}",
            structured_metadata={"currency": currency, "reused_from": prev.isoformat()},
        ))
        return [f"{d.isoformat()}:{currency}:USD"]


# --------------------------------------------------------------------------- #
# 3. Missing customer mapping
# --------------------------------------------------------------------------- #
class MissingCustomerMappingInjector(Injector):
    incident_type = IncidentType.MISSING_CUSTOMER_MAPPING

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        cust_ids = sorted(session.execute(select(Customer.customer_id)).scalars())
        n = 5
        targets = rng.sample(cust_ids, n)
        severity = compute_severity(
            affected_records=n, monetary_exposure=Decimal("0"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Customers missing CRM mapping",
            params={"customer_ids": targets},
            changed_tables=["customers", "system_logs"],
            affected_pipeline="customer_mapping_pipeline",
            expected_symptoms=[
                "customers.crm_customer_id is null for several customers",
                "Orders cannot be attributed via CRM",
            ],
            root_cause_description=(
                "The customer mapping pipeline dropped rows, leaving customers unmapped to CRM."
            ),
            expected_affected_systems=["CRM", "Customers", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:null_crm_mapping", "pipeline:customer_mapping_pipeline"],
            expected_remediation="Backfill customer-to-CRM mapping from CRM and reprocess.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        ids = manifest.params["customer_ids"]
        for cid in ids:
            c = session.get(Customer, cid)
            assert c is not None
            c.crm_customer_id = None
        session.add(SystemLog(
            log_id=f"LOG-INC-mapping-{manifest.manifest_id}",
            timestamp=_utc(_order_dates(session)[0], 2),
            service="PL-customer_mapping_pipeline",
            log_level="ERROR",
            message=f"Mapping step dropped {len(ids)} customer rows (CRM lookup miss)",
            correlation_id=f"map-{manifest.manifest_id}",
            pipeline_run_id=None,
            structured_metadata={"dropped": len(ids)},
        ))
        return list(ids)


# --------------------------------------------------------------------------- #
# 4. Schema change (simulated, no DDL)
# --------------------------------------------------------------------------- #
class SchemaChangeInjector(Injector):
    incident_type = IncidentType.SCHEMA_CHANGE

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        choice = rng.choice([
            ("orders", "gross_amount", "amount_gross"),
            ("payments", "payment_amount", "amount"),
            ("orders", "order_currency", "currency_code"),
        ])
        table, field, new_field = choice
        dates = _order_dates(session)
        d = rng.choice(dates[5:-5])
        severity = compute_severity(
            affected_records=200, monetary_exposure=Decimal("0"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title=f"Source renamed {table}.{field} -> {new_field}",
            params={"table": table, "field": field, "new_field": new_field, "date": d.isoformat()},
            changed_tables=["schema_events", "pipeline_runs", "system_logs", "staging_records"],
            affected_pipeline=f"{table}_ingest" if table == "orders" else "orders_ingest",
            expected_symptoms=[
                f"Ingestion failed: unknown column for {table}.{field}",
                "Schema-contract change event recorded",
            ],
            root_cause_description=(
                f"The source system renamed {table}.{field} to {new_field}; the staging mapping is "
                "incompatible, so the load failed the schema contract."
            ),
            expected_affected_systems=[table.capitalize(), "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=[
                "schema:contract_change", "pipeline:failed_run", "log:unknown_column",
            ],
            expected_remediation=(
                "Update the schema contract / staging field mapping and reprocess the staged batch."
            ),
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        p = manifest.params
        d = _as_date(p["date"])
        run_id = f"PR-INC-schema-{manifest.manifest_id}"
        session.add(SchemaEvent(
            event_id=f"SCHEMA-{manifest.manifest_id}",
            table_name=p["table"],
            change_type="column_renamed",
            field_name=p["field"],
            details=f"Source renamed '{p['field']}' to '{p['new_field']}'; mapping incompatible",
            pipeline_run_id=run_id,
            payload={"old": p["field"], "new": p["new_field"]},
            occurred_at=_utc(d, 2),
        ))
        from app.models import PipelineRun
        session.add(PipelineRun(
            pipeline_run_id=run_id,
            pipeline_id=f"PL-{manifest.affected_pipeline}",
            started_at=_utc(d, 2),
            completed_at=_utc(d, 2),
            status="failed",
            rows_read=0,
            rows_written=0,
            error_message=f"Unknown column '{p['new_field']}' (expected '{p['field']}')",
            run_metadata={"schema_event": f"SCHEMA-{manifest.manifest_id}"},
        ))
        session.add(StagingRecord(
            staging_id=f"STG-{manifest.manifest_id}",
            pipeline_run_id=run_id,
            source_system=p["table"],
            entity_type=p["table"].rstrip("s"),
            natural_key=None,
            payload={p["new_field"]: 100.0, "note": "renamed field present in source payload"},
            load_status="rejected",
            ingested_at=_utc(d, 2),
        ))
        session.add(SystemLog(
            log_id=f"LOG-INC-schema-{manifest.manifest_id}",
            timestamp=_utc(d, 2),
            service=f"PL-{manifest.affected_pipeline}",
            log_level="ERROR",
            message=f"Schema contract violation: unknown column '{p['new_field']}'",
            correlation_id=run_id,
            pipeline_run_id=run_id,
            structured_metadata={"field": p["field"], "new_field": p["new_field"]},
        ))
        return [f"SCHEMA-{manifest.manifest_id}"]


# --------------------------------------------------------------------------- #
# 5. Delayed pipeline
# --------------------------------------------------------------------------- #
class DelayedPipelineInjector(Injector):
    incident_type = IncidentType.DELAYED_PIPELINE

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        dates = _order_dates(session)
        d = rng.choice(dates[5:-5])
        severity = compute_severity(
            affected_records=1, monetary_exposure=Decimal("0"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Revenue report missing due to delayed upstream pipeline",
            params={"date": d.isoformat(), "pipeline": "revenue_aggregation_pipeline"},
            changed_tables=["pipeline_runs", "daily_revenue_report"],
            affected_pipeline="revenue_aggregation_pipeline",
            expected_symptoms=[
                "Pipeline run completed far beyond its window",
                "daily_revenue_report missing for the affected date",
            ],
            root_cause_description=(
                "An upstream ingest was delayed past the aggregation window, so the daily revenue "
                "report was not produced for the affected date."
            ),
            expected_affected_systems=["Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["pipeline:delayed_run", "sql:missing_report"],
            expected_remediation="Re-run the aggregation once the delayed ingest completes.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        from app.models import PipelineRun
        run = session.get(PipelineRun, f"PR-revenue_aggregation_pipeline-{d:%Y%m%d}")
        if run is not None:
            run.completed_at = run.started_at + timedelta(hours=14)
            run.status = "delayed"
            run.error_message = "Upstream ingest late; SLA breached"
        # Remove the report rows for that date (not produced in time).
        session.execute(delete(DailyRevenueReport).where(DailyRevenueReport.report_date == d))
        session.add(SystemLog(
            log_id=f"LOG-INC-delay-{manifest.manifest_id}",
            timestamp=_utc(d, 19),
            service="PL-revenue_aggregation_pipeline",
            log_level="ERROR",
            message=f"Aggregation for {d.isoformat()} skipped: upstream not ready (SLA breach)",
            correlation_id=f"delay-{d.isoformat()}",
            pipeline_run_id=f"PR-revenue_aggregation_pipeline-{d:%Y%m%d}",
            structured_metadata={"date": d.isoformat()},
        ))
        return [d.isoformat()]


# --------------------------------------------------------------------------- #
# 6. Timezone conversion error
# --------------------------------------------------------------------------- #
class TimezoneConversionErrorInjector(Injector):
    incident_type = IncidentType.TIMEZONE_CONVERSION_ERROR

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        region = "Asia"
        region_customers = set(session.execute(
            select(Customer.customer_id).where(Customer.region == region)
        ).scalars())
        # Candidate dates that actually have late-night Asia orders (hour >= 20).
        late_by_date: dict[date, int] = {}
        for o in session.execute(select(Order)).scalars():
            if o.customer_id in region_customers and o.order_timestamp.hour >= 20:
                d0 = o.order_timestamp.date()
                late_by_date[d0] = late_by_date.get(d0, 0) + 1
        dates = _order_dates(session)
        candidates = sorted(d0 for d0 in late_by_date if d0 in set(dates[5:-5]))
        d = rng.choice(candidates) if candidates else rng.choice(dates[5:-5])
        severity = compute_severity(
            affected_records=20, monetary_exposure=Decimal("80000"), downstream_reports=2,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Timezone conversion shifts revenue across day boundary",
            params={"date": d.isoformat(), "offset_hours": 6, "region": region},
            changed_tables=["orders"],
            affected_pipeline="revenue_aggregation_pipeline",
            expected_symptoms=[
                "Adjacent report days disagree with source (one over-, one under-counts)",
                "Late-night orders shifted into the next day",
            ],
            root_cause_description=(
                "Local source timestamps were treated as UTC, shifting late-night orders into the "
                "next day so daily revenue is misallocated across the day boundary."
            ),
            expected_affected_systems=["Orders", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:order_count_shift", "sql:reconciliation_mismatch"],
            expected_remediation="Normalize source timestamps to UTC and re-aggregate.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        offset = int(manifest.params["offset_hours"])
        region = manifest.params["region"]
        region_customers = set(session.execute(
            select(Customer.customer_id).where(Customer.region == region)
        ).scalars())
        start = _utc(d, 20)
        end = _utc(d, 23) + timedelta(hours=1)
        changed: list[str] = []
        orders = session.execute(
            select(Order).where(
                Order.order_timestamp >= start,
                Order.order_timestamp < end,
            )
        ).scalars()
        for o in orders:
            if o.customer_id in region_customers:
                o.order_timestamp = o.order_timestamp + timedelta(hours=offset)
                changed.append(o.order_id)
        return changed


# --------------------------------------------------------------------------- #
# 7. Null contamination (staging zone)
# --------------------------------------------------------------------------- #
class NullContaminationInjector(Injector):
    incident_type = IncidentType.NULL_CONTAMINATION

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        dates = _order_dates(session)
        d = rng.choice(dates[5:-5])
        n = 8
        severity = compute_severity(
            affected_records=n, monetary_exposure=Decimal("0"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Null gross_amount values in staged orders",
            params={"date": d.isoformat(), "count": n},
            changed_tables=["staging_records", "system_logs"],
            affected_pipeline="orders_ingest",
            expected_symptoms=[
                "Required field gross_amount is null in staged order records",
                "Validation errors logged during ingest",
            ],
            root_cause_description=(
                "The source delivered orders with a null required field (gross_amount); the rows "
                "landed in staging instead of being rejected."
            ),
            expected_affected_systems=["Orders", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:null_required_field", "log:validation_error"],
            expected_remediation="Quarantine null staged rows, fix the source feed, and reload.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        n = int(manifest.params["count"])
        run_id = f"PR-orders_ingest-{d:%Y%m%d}"
        changed: list[str] = []
        for i in range(n):
            sid = f"STG-NULL-{manifest.manifest_id}-{i:02d}"
            session.add(StagingRecord(
                staging_id=sid,
                pipeline_run_id=run_id,
                source_system="Orders",
                entity_type="order",
                natural_key=f"ORD-STAGED-{manifest.manifest_id}-{i:02d}",
                payload={
                    "order_id": f"ORD-STAGED-{i:02d}", "gross_amount": None, "currency": "EUR",
                },
                load_status="loaded",
                ingested_at=_utc(d, 3),
            ))
            changed.append(sid)
        session.add(SystemLog(
            log_id=f"LOG-INC-null-{manifest.manifest_id}",
            timestamp=_utc(d, 3),
            service="PL-orders_ingest",
            log_level="ERROR",
            message=f"Validation error: gross_amount is null in {n} staged order records",
            correlation_id=run_id,
            pipeline_run_id=run_id,
            structured_metadata={"null_field": "gross_amount", "count": n},
        ))
        return changed


# --------------------------------------------------------------------------- #
# 8. Partial load
# --------------------------------------------------------------------------- #
class PartialLoadInjector(Injector):
    incident_type = IncidentType.PARTIAL_LOAD

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        dates = _order_dates(session)
        d = rng.choice(dates[5:-5])
        severity = compute_severity(
            affected_records=100, monetary_exposure=Decimal("150000"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Partial file load drops most orders for a day",
            params={"date": d.isoformat(), "drop_fraction": 0.7},
            changed_tables=["orders", "payments", "refunds", "shipments", "pipeline_runs"],
            affected_pipeline="orders_ingest",
            expected_symptoms=[
                "Order row count for the day far below the daily norm",
                "rows_written far below rows_read for the ingest run",
            ],
            root_cause_description=(
                "The order ingest file was truncated mid-stream, so most of the day's orders were "
                "never loaded."
            ),
            expected_affected_systems=["Orders", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:row_count_drop", "pipeline:partial_run"],
            expected_remediation="Reload the complete file and verify row counts.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        frac = float(manifest.params["drop_fraction"])
        start = _utc(d, 0)
        end = start + timedelta(days=1)
        order_ids = sorted(session.execute(
            select(Order.order_id).where(
                Order.order_timestamp >= start, Order.order_timestamp < end
            )
        ).scalars())
        rng = random.Random(stable_seed(manifest.seed, "partial", manifest.index))
        rng.shuffle(order_ids)
        drop = order_ids[: int(len(order_ids) * frac)]
        drop_set = set(drop)
        # Delete dependents first (FK-safe): refunds, payments, shipments, then orders.
        session.execute(delete(Refund).where(Refund.order_id.in_(drop_set)))
        session.execute(delete(Payment).where(Payment.order_id.in_(drop_set)))
        session.execute(delete(Shipment).where(Shipment.order_id.in_(drop_set)))
        session.execute(delete(Order).where(Order.order_id.in_(drop_set)))
        from app.models import PipelineRun
        run = session.get(PipelineRun, f"PR-orders_ingest-{d:%Y%m%d}")
        if run is not None:
            run.rows_written = max(1, run.rows_read - len(drop) * 10)
            run.status = "completed"
            run.run_metadata = {"partial": True, "dropped_orders": len(drop)}
        session.add(SystemLog(
            log_id=f"LOG-INC-partial-{manifest.manifest_id}",
            timestamp=_utc(d, 4),
            service="PL-orders_ingest",
            log_level="WARN",
            message=f"Truncated input: loaded partial batch, dropped {len(drop)} orders",
            correlation_id=f"partial-{d.isoformat()}",
            pipeline_run_id=f"PR-orders_ingest-{d:%Y%m%d}",
            structured_metadata={"dropped": len(drop)},
        ))
        return drop


# --------------------------------------------------------------------------- #
# 9. Incorrect aggregation
# --------------------------------------------------------------------------- #
class IncorrectAggregationInjector(Injector):
    incident_type = IncidentType.INCORRECT_AGGREGATION

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        reports = session.execute(
            select(DailyRevenueReport.report_date, DailyRevenueReport.region)
            .where(DailyRevenueReport.refund_total > 0)
        ).all()
        report_keys = sorted({(_as_date(r[0]).isoformat(), r[1]) for r in reports})
        target = rng.choice(report_keys)
        severity = compute_severity(
            affected_records=1, monetary_exposure=Decimal("120000"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Refund sign error in revenue aggregation",
            params={"date": target[0], "region": target[1]},
            changed_tables=["daily_revenue_report"],
            affected_pipeline="revenue_aggregation_pipeline",
            expected_symptoms=[
                "net_revenue != gross_revenue - refund_total in the report",
                "Report does not reconcile to source",
            ],
            root_cause_description=(
                "The aggregation added refunds instead of subtracting them, so net revenue is "
                "overstated by twice the refund total."
            ),
            expected_affected_systems=["Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["sql:net_revenue_inconsistent", "sql:reconciliation_mismatch"],
            expected_remediation="Fix the aggregation refund sign and recompute the report.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        region = manifest.params["region"]
        rep = session.get(DailyRevenueReport, (d, region))
        if rep is not None:
            rep.net_revenue = rep.gross_revenue + rep.refund_total  # wrong sign
        return [f"{d.isoformat()}:{region}"]


# --------------------------------------------------------------------------- #
# 10. Upstream API failure
# --------------------------------------------------------------------------- #
class UpstreamApiFailureInjector(Injector):
    incident_type = IncidentType.UPSTREAM_API_FAILURE

    def plan(self, session: Session, seed: int, index: int) -> IncidentManifest:
        rng = self.rng(seed, index)
        dates = _order_dates(session)
        d = rng.choice(dates[5:-5])
        severity = compute_severity(
            affected_records=30, monetary_exposure=Decimal("90000"), downstream_reports=1,
            incident_type=self.incident_type,
        )
        return self._manifest(
            index=index, seed=seed,
            title="Payment provider API error burst causes missing payments",
            params={"date": d.isoformat(), "error_count": 25},
            changed_tables=["system_logs", "pipeline_runs", "payments", "refunds"],
            affected_pipeline="payment_reconciliation_pipeline",
            expected_symptoms=[
                "Burst of 5xx errors from the payment provider",
                "Failed payment reconciliation run; some payments missing",
            ],
            root_cause_description=(
                "The payment provider API returned a burst of 5xx errors, so a window of payments "
                "failed to ingest."
            ),
            expected_affected_systems=["Payments", "Reporting"],
            expected_affected_reports=["daily_revenue_report"],
            expected_evidence=["log:api_error_burst", "pipeline:failed_run"],
            expected_remediation="Replay the failed payment windows once the provider recovers.",
            severity=severity,
        )

    def apply(self, session: Session, manifest: IncidentManifest) -> list[str]:
        d = _as_date(manifest.params["date"])
        count = int(manifest.params["error_count"])
        run_id = f"PR-INC-api-{manifest.manifest_id}"
        changed: list[str] = []
        for i in range(count):
            lid = f"LOG-INC-api-{manifest.manifest_id}-{i:03d}"
            session.add(SystemLog(
                log_id=lid,
                timestamp=_utc(d, 3) + timedelta(minutes=i),
                service="payment_provider_api",
                log_level="ERROR",
                message=f"HTTP 503 from payment provider (attempt {i})",
                correlation_id=run_id,
                pipeline_run_id=run_id,
                structured_metadata={"status": 503, "attempt": i},
            ))
            changed.append(lid)
        from app.models import PipelineRun
        session.add(PipelineRun(
            pipeline_run_id=run_id,
            pipeline_id="PL-payment_reconciliation_pipeline",
            started_at=_utc(d, 3),
            completed_at=_utc(d, 3) + timedelta(minutes=count),
            status="failed",
            rows_read=count,
            rows_written=0,
            error_message="Payment provider API unavailable (HTTP 503 burst)",
            run_metadata={"error_count": count},
        ))
        # A small window of payments fails to ingest (delete a few, FK-safe).
        start = _utc(d, 3)
        end = _utc(d, 5)
        pay_ids = sorted(session.execute(
            select(Payment.payment_id).where(
                Payment.payment_timestamp >= start, Payment.payment_timestamp < end
            )
        ).scalars())[:5]
        if pay_ids:
            session.execute(delete(Refund).where(Refund.payment_id.in_(pay_ids)))
            session.execute(delete(Payment).where(Payment.payment_id.in_(pay_ids)))
            changed.extend(pay_ids)
        return changed


INJECTORS: dict[IncidentType, type[Injector]] = {
    IncidentType.DUPLICATE_TRANSACTION: DuplicateTransactionInjector,
    IncidentType.STALE_FX_RATE: StaleFxRateInjector,
    IncidentType.MISSING_CUSTOMER_MAPPING: MissingCustomerMappingInjector,
    IncidentType.SCHEMA_CHANGE: SchemaChangeInjector,
    IncidentType.DELAYED_PIPELINE: DelayedPipelineInjector,
    IncidentType.TIMEZONE_CONVERSION_ERROR: TimezoneConversionErrorInjector,
    IncidentType.NULL_CONTAMINATION: NullContaminationInjector,
    IncidentType.PARTIAL_LOAD: PartialLoadInjector,
    IncidentType.INCORRECT_AGGREGATION: IncorrectAggregationInjector,
    IncidentType.UPSTREAM_API_FAILURE: UpstreamApiFailureInjector,
}


def get_injector(incident_type: IncidentType) -> Injector:
    return INJECTORS[incident_type]()
