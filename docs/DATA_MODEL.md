# LineageIQ — Data Model

All money is stored as `NUMERIC` (Python `Decimal`). All timestamps are UTC.

## Business tables
- **customers** — customer_id, legal_name, country, region, base_currency, crm_customer_id,
  created_at, status
- **crm_customers** — crm_customer_id, external_customer_reference, legal_name, country, segment,
  updated_at
- **customer_limits** — limit_id, customer_id, currency, credit_limit, effective_from,
  effective_to, updated_at
- **orders** — order_id, customer_id, order_timestamp, order_currency, gross_amount, net_amount,
  tax_amount, order_status, source_system, updated_at
- **payments** — payment_id, order_id, customer_id, payment_timestamp, payment_currency,
  payment_amount, payment_status, payment_provider, idempotency_key, updated_at
- **refunds** — refund_id, payment_id, order_id, customer_id, refund_timestamp, refund_currency,
  refund_amount, refund_reason, refund_status, updated_at
- **fx_rates** — rate_date, source_currency, target_currency, exchange_rate, provider,
  retrieved_at (PK: rate_date+source+target+provider)
- **shipments** — shipment_id, order_id, warehouse_region, carrier, shipment_status, shipped_at,
  delivered_at, updated_at
- **daily_revenue_report** — report_date, region, reporting_currency, gross_revenue, refund_total,
  net_revenue, order_count, payment_count, generated_at, source_pipeline_run_id

## Operational tables
- **pipeline_definitions** — pipeline_id, pipeline_name, source_system, target_system, schedule,
  owner, active
- **pipeline_runs** — pipeline_run_id, pipeline_id, started_at, completed_at, status, rows_read,
  rows_written, error_message, metadata (JSON)
- **system_logs** — log_id, timestamp, service, log_level, message, correlation_id,
  pipeline_run_id, structured_metadata (JSON)
- **incidents** — incident_id, title, detected_at, status, severity, source_alert_id,
  primary_affected_system, assigned_to, created_at, resolved_at
- **alerts** — alert_id, detector_name, detected_at, entity_type, entity_id, metric_name,
  observed_value, expected_value, anomaly_score, severity, metadata (JSON)
- **evidence** — evidence_id, incident_id, evidence_type, source, summary, raw_reference,
  collected_at, reliability_score, structured_payload (JSON)
- **agent_runs** — agent_run_id, incident_id, started_at, completed_at, status, model_name,
  tool_call_count, prompt_tokens, completion_tokens, estimated_cost, trace_id, output (JSON),
  failure_reason
- **incident_ground_truth** — incident_id, injected_incident_type, root_cause_code,
  root_cause_description, affected_tables, affected_jobs, affected_reports, expected_evidence,
  should_escalate, injection_manifest (JSON), created_at
- **historical_incidents** — historical_incident_id, title, incident_type, symptoms, root_cause,
  affected_systems, remediation, severity, evidence_summary, searchable_text, occurred_at
- **evaluation_runs** — evaluation_run_id, started_at, completed_at, dataset_version, model_name,
  configuration (JSON), metrics (JSON), report_path

## Referential integrity (clean baseline invariants)
- Every order.customer_id ∈ customers; every customer.crm_customer_id ∈ crm_customers.
- Every payment.order_id ∈ orders; payment.customer_id == order.customer_id.
- Every refund.payment_id ∈ payments; refund.amount ≤ payment.amount.
- Every shipment.order_id ∈ orders.
- order.net_amount + order.tax_amount == order.gross_amount.
- FX rates exist for every (date, currency→reporting_currency) used by reports.
- daily_revenue_report values reconcile to source orders/payments/refunds (converted via FX).
- No NULLs in required columns; no duplicate payment_id or idempotency_key.

These invariants are asserted by `make validate-data` and are what incident injectors violate.
