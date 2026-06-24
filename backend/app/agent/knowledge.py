"""Per-root-cause investigation playbooks, remediation, and recommended checks.

The FakeLLM uses these to drive a deterministic, evidence-gathering investigation. A real LLM would
choose tools itself; this keeps tests/CI fully offline and reproducible.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.agent.types import ToolInvocation
from app.core.taxonomy import RootCauseCode


def _date(meta: dict[str, Any]) -> date | None:
    raw = meta.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _lineage(node: str | None, direction: str = "downstream") -> ToolInvocation | None:
    if not node:
        return None
    return ToolInvocation(
        "query_lineage", {"start_node": node, "direction": direction},
        f"Map {direction} lineage from {node} to find impacted assets",
    )


def _historical(symptoms: str, incident_type: str) -> ToolInvocation:
    return ToolInvocation(
        "search_historical_incidents",
        {"symptoms": symptoms, "suspected_incident_type": incident_type, "max_results": 3},
        "Retrieve similar historical incidents and their remediations",
    )


def build_playbook(
    cause: RootCauseCode, meta: dict[str, Any], focus_node: str | None
) -> list[ToolInvocation]:
    """Return the ordered tool plan for a suspected root cause."""
    d = _date(meta)
    steps: list[ToolInvocation | None] = []

    if cause == RootCauseCode.STALE_FX_RATE:
        cur = meta.get("currency", "EUR")
        where = f"source_currency = '{cur}' AND target_currency = 'USD'"
        if d:
            lo, hi = d - timedelta(days=3), d + timedelta(days=1)
            where += f" AND rate_date BETWEEN '{lo}' AND '{hi}'"
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": f"SELECT rate_date, source_currency, exchange_rate FROM fx_rates "
                         f"WHERE {where} ORDER BY rate_date",
                "reason": "Compare FX rates around the suspected date for missing drift",
            }, "Check whether the FX rate failed to update"),
            ToolInvocation("inspect_pipeline_runs", {"pipeline": "fx_rate_pipeline"},
                           "Inspect FX pipeline runs for reuse/low row counts"),
            ToolInvocation("search_logs", {
                "service": "PL-fx_rate_pipeline",
                "search_terms": ["stale", "reuse", "rate"]},
                "Find logs indicating the FX rate was reused"),
            _lineage(focus_node or "fx_rates"),
            _historical("stale fx rate revenue overstated", "stale_fx_rate"),
        ]
    elif cause == RootCauseCode.DUPLICATE_TRANSACTION:
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": "SELECT idempotency_key, COUNT(*) AS c FROM payments "
                         "GROUP BY idempotency_key HAVING COUNT(*) > 1",
                "reason": "Find payments sharing an idempotency key (duplicates)",
            }, "Detect duplicate payments"),
            ToolInvocation("search_logs", {
                "service": "PL-payment_reconciliation_pipeline",
                "search_terms": ["retry", "idempotency"]},
                "Look for retry logs without dedupe"),
            _lineage(focus_node or "payments"),
            _historical("duplicate payment double counted", "duplicate_transaction"),
        ]
    elif cause == RootCauseCode.MISSING_CUSTOMER_MAPPING:
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": "SELECT customer_id FROM customers WHERE crm_customer_id IS NULL",
                "reason": "List customers missing a CRM mapping",
            }, "Quantify unmapped customers"),
            ToolInvocation("inspect_pipeline_runs", {"pipeline": "customer_mapping_pipeline"},
                           "Inspect the customer mapping pipeline"),
            _lineage(focus_node or "customers"),
            _historical("missing customer mapping unattributed", "missing_customer_mapping"),
        ]
    elif cause == RootCauseCode.SCHEMA_CONTRACT_CHANGE:
        steps = [
            ToolInvocation("inspect_schema", {"table": meta.get("table", "orders")},
                           "Inspect the table schema + recent schema events"),
            ToolInvocation("inspect_pipeline_runs", {"status": "failed"},
                           "Find failed ingest runs"),
            ToolInvocation("search_logs", {"search_terms": ["schema", "column"]},
                           "Find schema-contract violation logs"),
            _lineage(focus_node or "orders"),
            _historical("schema contract change ingestion failed", "schema_change"),
        ]
    elif cause == RootCauseCode.DELAYED_PIPELINE:
        steps = [
            ToolInvocation("inspect_pipeline_runs", {"pipeline": "revenue_aggregation_pipeline"},
                           "Inspect the aggregation pipeline for delays"),
            ToolInvocation("search_logs", {"search_terms": ["delay", "sla", "skipped"]},
                           "Find SLA/delay logs"),
            _lineage(focus_node or "revenue_aggregation_pipeline"),
            _historical("delayed pipeline report missing", "delayed_pipeline"),
        ]
    elif cause == RootCauseCode.TIMEZONE_CONVERSION_ERROR:
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": "SELECT report_date, region, order_count FROM daily_revenue_report "
                         "ORDER BY region, report_date",
                "reason": "Inspect order counts by day/region for a shift pattern",
            }, "Look for a day-boundary shift"),
            _lineage(focus_node or "orders"),
            _historical("timezone conversion shifted revenue", "timezone_conversion_error"),
        ]
    elif cause == RootCauseCode.NULL_CONTAMINATION:
        steps = [
            ToolInvocation("search_logs", {
                "service": "PL-orders_ingest",
                "search_terms": ["null", "validation"]},
                "Find null-field validation errors"),
            ToolInvocation("inspect_schema", {"table": "orders"},
                           "Confirm required (non-null) fields"),
            _lineage(focus_node or "staging_records"),
            _historical("null contamination required field", "null_contamination"),
        ]
    elif cause == RootCauseCode.PARTIAL_LOAD:
        where = ""
        if d:
            nxt = d + timedelta(days=1)
            where = f" WHERE order_timestamp >= '{d}' AND order_timestamp < '{nxt}'"
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": f"SELECT order_id FROM orders{where}",
                "reason": "Count orders loaded for the suspected day",
            }, "Check for a truncated load"),
            ToolInvocation("inspect_pipeline_runs", {"pipeline": "orders_ingest"},
                           "Inspect ingest run row counts"),
            _lineage(focus_node or "orders"),
            _historical("partial load truncated file", "partial_load"),
        ]
    elif cause == RootCauseCode.INCORRECT_AGGREGATION:
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": "SELECT report_date, region, gross_revenue, refund_total, net_revenue "
                         "FROM daily_revenue_report "
                         "WHERE net_revenue <> gross_revenue - refund_total",
                "reason": "Find report rows where net != gross - refund",
            }, "Detect aggregation inconsistency"),
            _lineage(focus_node or "revenue_aggregation_pipeline"),
            _historical("incorrect aggregation net revenue", "incorrect_aggregation"),
        ]
    elif cause == RootCauseCode.UPSTREAM_API_FAILURE:
        steps = [
            ToolInvocation("search_logs", {
                "service": "payment_provider_api", "log_levels": ["ERROR"]},
                "Find the API error burst"),
            ToolInvocation("inspect_pipeline_runs", {"status": "failed"},
                           "Find the failed reconciliation run"),
            _lineage(focus_node or "payment_provider_api"),
            _historical("upstream api failure missing payments", "upstream_api_failure"),
        ]
    else:  # UNKNOWN / fallback
        steps = [
            ToolInvocation("run_readonly_sql", {
                "query": "SELECT report_date, region, gross_revenue, net_revenue "
                         "FROM daily_revenue_report ORDER BY report_date",
                "reason": "Inspect the revenue report",
            }, "Examine the affected report"),
            _lineage(focus_node or "daily_revenue_report", "upstream"),
            _historical("revenue reconciliation mismatch", "unknown"),
        ]

    return [s for s in steps if s is not None]


# action, target_system, risk
REMEDIATION: dict[RootCauseCode, tuple[str, str, str]] = {
    RootCauseCode.STALE_FX_RATE: (
        "Refresh FX rates for the affected date and regenerate affected revenue reports",
        "ForeignExchange", "medium"),
    RootCauseCode.DUPLICATE_TRANSACTION: (
        "Deduplicate payments by idempotency_key and rebuild affected aggregates",
        "Payments", "high"),
    RootCauseCode.MISSING_CUSTOMER_MAPPING: (
        "Backfill customer-to-CRM mapping and reprocess attribution", "CRM", "medium"),
    RootCauseCode.SCHEMA_CONTRACT_CHANGE: (
        "Update the schema contract / staging field mapping and reprocess the staged batch",
        "Orders", "high"),
    RootCauseCode.DELAYED_PIPELINE: (
        "Re-run the aggregation once the delayed upstream ingest completes", "Reporting", "low"),
    RootCauseCode.TIMEZONE_CONVERSION_ERROR: (
        "Normalize source timestamps to UTC and re-aggregate the affected days",
        "Orders", "medium"),
    RootCauseCode.NULL_CONTAMINATION: (
        "Quarantine null staged rows, fix the source feed, and reload", "Orders", "medium"),
    RootCauseCode.PARTIAL_LOAD: (
        "Reload the complete source file and verify row counts", "Orders", "high"),
    RootCauseCode.INCORRECT_AGGREGATION: (
        "Fix the aggregation logic (refund sign) and recompute the report", "Reporting", "high"),
    RootCauseCode.UPSTREAM_API_FAILURE: (
        "Replay the failed payment windows once the provider recovers", "Payments", "medium"),
    RootCauseCode.UNKNOWN: (
        "Escalate for manual investigation; insufficient evidence for automated remediation",
        "Reporting", "low"),
}
