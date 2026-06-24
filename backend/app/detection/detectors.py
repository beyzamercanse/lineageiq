"""Deterministic detection controls.

Each detector inspects the database and emits standardized ``AlertDTO`` objects. Detectors are
exact reconciliation/consistency rules (no ML) — they double as the automated baseline and as
ground-truth-free symptom finders. One category-specific detector exists per incident type, plus a
generic revenue-reconciliation detector that corroborates several categories.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import RootCauseCode, Severity
from app.detection.reconcile import load_reports, recompute_from_source
from app.models import (
    Customer,
    Order,
    Payment,
    PipelineRun,
    SchemaEvent,
    StagingRecord,
    SystemLog,
)
from app.schemas.detection import AlertDTO


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Detector:
    name: str

    def run(self, session: Session) -> list[AlertDTO]:  # pragma: no cover - interface
        raise NotImplementedError


class DuplicatePaymentDetector(Detector):
    name = "duplicate_payment_control"

    def run(self, session: Session) -> list[AlertDTO]:
        rows = session.execute(
            select(Payment.idempotency_key, func.count())
            .group_by(Payment.idempotency_key)
            .having(func.count() > 1)
        ).all()
        alerts = []
        for key, count in rows:
            alerts.append(AlertDTO(
                detector_name=self.name, entity_type="idempotency_key", entity_id=str(key),
                metric_name="duplicate_payment_count", observed_value=str(count),
                expected_value="1", anomaly_score=1.0, severity=Severity.HIGH,
                suspected_root_cause=RootCauseCode.DUPLICATE_TRANSACTION, detected_at=_now(),
                metadata={"idempotency_key": key},
            ))
        return alerts


class StaleFxRateDetector(Detector):
    name = "stale_fx_rate_control"

    def run(self, session: Session) -> list[AlertDTO]:
        from app.models import FxRate

        by_pair: dict[tuple[str, str], list] = defaultdict(list)
        for r in session.execute(select(FxRate)).scalars():
            by_pair[(r.source_currency, r.target_currency)].append(r)
        alerts = []
        for (src, tgt), rates in by_pair.items():
            if src == tgt:
                continue
            rates.sort(key=lambda x: x.rate_date)
            for prev, cur in zip(rates, rates[1:]):
                if cur.exchange_rate == prev.exchange_rate:
                    alerts.append(AlertDTO(
                        detector_name=self.name, entity_type="fx_rate",
                        entity_id=f"{cur.rate_date.isoformat()}:{src}:{tgt}",
                        metric_name="fx_rate_drift", observed_value="0.0",
                        expected_value=">0", anomaly_score=1.0, severity=Severity.HIGH,
                        suspected_root_cause=RootCauseCode.STALE_FX_RATE, detected_at=_now(),
                        metadata={"currency": src, "date": cur.rate_date.isoformat(),
                                  "reused_from": prev.rate_date.isoformat()},
                    ))
        return alerts


class MissingCustomerMappingDetector(Detector):
    name = "missing_customer_mapping_control"

    def run(self, session: Session) -> list[AlertDTO]:
        count = session.scalar(
            select(func.count()).select_from(Customer).where(Customer.crm_customer_id.is_(None))
        ) or 0
        if count == 0:
            return []
        return [AlertDTO(
            detector_name=self.name, entity_type="customers", entity_id="crm_mapping",
            metric_name="null_crm_mapping_count", observed_value=str(count), expected_value="0",
            anomaly_score=1.0, severity=Severity.MEDIUM,
            suspected_root_cause=RootCauseCode.MISSING_CUSTOMER_MAPPING, detected_at=_now(),
            metadata={"null_count": count},
        )]


class SchemaChangeDetector(Detector):
    name = "schema_contract_control"

    def run(self, session: Session) -> list[AlertDTO]:
        alerts = []
        for e in session.execute(select(SchemaEvent)).scalars():
            alerts.append(AlertDTO(
                detector_name=self.name, entity_type="schema_event", entity_id=e.event_id,
                metric_name="schema_contract_change", observed_value=e.change_type,
                expected_value="stable", anomaly_score=1.0, severity=Severity.HIGH,
                suspected_root_cause=RootCauseCode.SCHEMA_CONTRACT_CHANGE, detected_at=_now(),
                metadata={"table": e.table_name, "field": e.field_name},
            ))
        return alerts


class DelayedPipelineDetector(Detector):
    name = "delayed_pipeline_control"
    max_duration_hours = 3

    def run(self, session: Session) -> list[AlertDTO]:
        alerts = []
        for run in session.execute(select(PipelineRun)).scalars():
            delayed = run.status in ("delayed", "running")
            duration_h = None
            if run.completed_at is not None:
                duration_h = (run.completed_at - run.started_at).total_seconds() / 3600.0
                if duration_h > self.max_duration_hours:
                    delayed = True
            if delayed:
                alerts.append(AlertDTO(
                    detector_name=self.name, entity_type="pipeline_run",
                    entity_id=run.pipeline_run_id, metric_name="run_duration_hours",
                    observed_value=f"{duration_h:.1f}" if duration_h else run.status,
                    expected_value=f"<{self.max_duration_hours}", anomaly_score=0.9,
                    severity=Severity.MEDIUM,
                    suspected_root_cause=RootCauseCode.DELAYED_PIPELINE, detected_at=_now(),
                    metadata={"pipeline_id": run.pipeline_id, "status": run.status},
                ))
        # Missing report for a date that has source orders.
        source_dates = {
            d for (d,) in (
                (o.order_timestamp.date(),) for o in session.execute(select(Order)).scalars()
            )
        }
        report_dates = {k[0] for k in load_reports(session)}
        for d in sorted(source_dates - report_dates):
            alerts.append(AlertDTO(
                detector_name=self.name, entity_type="daily_revenue_report",
                entity_id=d.isoformat(), metric_name="report_present", observed_value="missing",
                expected_value="present", anomaly_score=0.95, severity=Severity.MEDIUM,
                suspected_root_cause=RootCauseCode.DELAYED_PIPELINE, detected_at=_now(),
                metadata={"date": d.isoformat()},
            ))
        return alerts


class TimezoneShiftDetector(Detector):
    name = "timezone_shift_control"

    def run(self, session: Session) -> list[AlertDTO]:
        recomputed = recompute_from_source(session)
        reports = load_reports(session)
        # diff per (date, region) = report.order_count - source.order_count
        diffs: dict[str, dict[date, int]] = defaultdict(dict)
        for (d, region), rc in recomputed.items():
            rep = reports.get((d, region))
            if rep is None:
                continue
            diffs[region][d] = rep.order_count - rc.order_count
        alerts = []
        for region, by_date in diffs.items():
            dates = sorted(by_date)
            for d0, d1 in zip(dates, dates[1:]):
                if (d1 - d0).days != 1:
                    continue
                a, b = by_date[d0], by_date[d1]
                # Opposite-signed adjacent diffs of similar magnitude => day-boundary shift.
                if a > 0 and b < 0 and abs(abs(a) - abs(b)) <= max(2, int(0.5 * abs(a))):
                    alerts.append(AlertDTO(
                        detector_name=self.name, entity_type="daily_revenue_report",
                        entity_id=f"{region}:{d0.isoformat()}", metric_name="order_count_shift",
                        observed_value=f"{a}/{b}", expected_value="0/0", anomaly_score=0.85,
                        severity=Severity.MEDIUM,
                        suspected_root_cause=RootCauseCode.TIMEZONE_CONVERSION_ERROR,
                        detected_at=_now(),
                        metadata={"region": region, "date": d0.isoformat(),
                                  "next_date": d1.isoformat()},
                    ))
        return alerts


_REQUIRED_STAGING_FIELDS = {"order": "gross_amount", "payment": "payment_amount"}


class NullContaminationDetector(Detector):
    name = "null_contamination_control"

    def run(self, session: Session) -> list[AlertDTO]:
        counts: dict[str, int] = defaultdict(int)
        for rec in session.execute(select(StagingRecord)).scalars():
            field = _REQUIRED_STAGING_FIELDS.get(rec.entity_type)
            if field and rec.payload.get(field) is None:
                counts[f"{rec.entity_type}.{field}"] += 1
        alerts = []
        for field, count in counts.items():
            alerts.append(AlertDTO(
                detector_name=self.name, entity_type="staging_records", entity_id=field,
                metric_name="null_required_field_count", observed_value=str(count),
                expected_value="0", anomaly_score=1.0, severity=Severity.MEDIUM,
                suspected_root_cause=RootCauseCode.NULL_CONTAMINATION, detected_at=_now(),
                metadata={"field": field, "count": count},
            ))
        return alerts


class PartialLoadDetector(Detector):
    name = "partial_load_control"

    def run(self, session: Session) -> list[AlertDTO]:
        per_day: dict[date, int] = defaultdict(int)
        for o in session.execute(select(Order)).scalars():
            per_day[o.order_timestamp.date()] += 1
        if len(per_day) < 5:
            return []
        med = statistics.median(per_day.values())
        if med <= 0:
            return []
        alerts = []
        for d in sorted(per_day):
            count = per_day[d]
            if count < 0.5 * med:
                alerts.append(AlertDTO(
                    detector_name=self.name, entity_type="orders", entity_id=d.isoformat(),
                    metric_name="daily_order_count", observed_value=str(count),
                    expected_value=f"~{int(med)}", anomaly_score=0.9, severity=Severity.HIGH,
                    suspected_root_cause=RootCauseCode.PARTIAL_LOAD, detected_at=_now(),
                    metadata={"date": d.isoformat(), "median": int(med)},
                ))
        return alerts


class IncorrectAggregationDetector(Detector):
    name = "aggregation_consistency_control"

    def run(self, session: Session) -> list[AlertDTO]:
        alerts = []
        for (d, region), rep in load_reports(session).items():
            if rep.net_revenue != rep.gross_revenue - rep.refund_total:
                alerts.append(AlertDTO(
                    detector_name=self.name, entity_type="daily_revenue_report",
                    entity_id=f"{region}:{d.isoformat()}", metric_name="net_revenue_consistency",
                    observed_value=str(rep.net_revenue),
                    expected_value=str(rep.gross_revenue - rep.refund_total),
                    anomaly_score=1.0, severity=Severity.HIGH,
                    suspected_root_cause=RootCauseCode.INCORRECT_AGGREGATION, detected_at=_now(),
                    metadata={"region": region, "date": d.isoformat()},
                ))
        return alerts


class ApiErrorBurstDetector(Detector):
    name = "api_error_burst_control"
    threshold = 10

    def run(self, session: Session) -> list[AlertDTO]:
        counts: dict[tuple[str, date], int] = defaultdict(int)
        for log in session.execute(
            select(SystemLog).where(SystemLog.log_level == "ERROR")
        ).scalars():
            counts[(log.service, log.timestamp.date())] += 1
        alerts = []
        for (service, d), count in counts.items():
            if count >= self.threshold:
                alerts.append(AlertDTO(
                    detector_name=self.name, entity_type="system_logs",
                    entity_id=f"{service}:{d.isoformat()}", metric_name="error_log_count",
                    observed_value=str(count), expected_value=f"<{self.threshold}",
                    anomaly_score=0.9, severity=Severity.HIGH,
                    suspected_root_cause=RootCauseCode.UPSTREAM_API_FAILURE, detected_at=_now(),
                    metadata={"service": service, "date": d.isoformat(), "count": count},
                ))
        return alerts


class RevenueReconciliationDetector(Detector):
    """Generic: published report disagrees with source. Corroborates several categories."""

    name = "revenue_reconciliation_control"

    def run(self, session: Session) -> list[AlertDTO]:
        recomputed = recompute_from_source(session)
        reports = load_reports(session)
        alerts = []
        for key, rep in reports.items():
            rc = recomputed.get(key)
            if rc is None:
                continue
            if (
                rep.gross_revenue != rc.gross
                or rep.refund_total != rc.refund_total
                or rep.order_count != rc.order_count
                or rep.payment_count != rc.payment_count
            ):
                d, region = key
                alerts.append(AlertDTO(
                    detector_name=self.name, entity_type="daily_revenue_report",
                    entity_id=f"{region}:{d.isoformat()}", metric_name="revenue_reconciliation",
                    observed_value=str(rep.gross_revenue), expected_value=str(rc.gross),
                    anomaly_score=0.8, severity=Severity.MEDIUM,
                    suspected_root_cause=RootCauseCode.UNKNOWN, detected_at=_now(),
                    metadata={"region": region, "date": d.isoformat(),
                              "report_orders": rep.order_count, "source_orders": rc.order_count},
                ))
        return alerts


ALL_DETECTORS: list[Detector] = [
    DuplicatePaymentDetector(),
    StaleFxRateDetector(),
    MissingCustomerMappingDetector(),
    SchemaChangeDetector(),
    DelayedPipelineDetector(),
    TimezoneShiftDetector(),
    NullContaminationDetector(),
    PartialLoadDetector(),
    IncorrectAggregationDetector(),
    ApiErrorBurstDetector(),
    RevenueReconciliationDetector(),
]


def run_all_detectors(session: Session) -> list[AlertDTO]:
    alerts: list[AlertDTO] = []
    for detector in ALL_DETECTORS:
        alerts.extend(detector.run(session))
    return alerts
