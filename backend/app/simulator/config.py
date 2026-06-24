"""Generator configuration and domain constants.

The simulation is anchored to a FIXED start date (not "today") so that generation is fully
deterministic and reproducible across runs and machines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Reporting currency for the consolidated daily revenue report.
REPORTING_CURRENCY = "USD"

CURRENCIES = ["USD", "EUR", "GBP", "TRY", "JPY"]

# region -> (countries, default currency, tax rate)
REGIONS: dict[str, dict] = {
    "Europe": {"countries": ["DE", "FR", "GB", "ES", "IT"], "tax_rate": "0.20"},
    "NorthAmerica": {"countries": ["US", "CA", "MX"], "tax_rate": "0.08"},
    "Asia": {"countries": ["JP", "TR", "SG", "IN"], "tax_rate": "0.10"},
}

# country -> base currency
COUNTRY_CURRENCY = {
    "DE": "EUR", "FR": "EUR", "ES": "EUR", "IT": "EUR",
    "GB": "GBP",
    "US": "USD", "CA": "USD", "MX": "USD",
    "JP": "JPY",
    "TR": "TRY",
    "SG": "USD", "IN": "USD",
}

CUSTOMER_SEGMENTS = ["enterprise", "mid_market", "smb"]
PAYMENT_PROVIDERS = ["stripe", "adyen", "braintree"]
CARRIERS = ["DHL", "FedEx", "UPS", "Aramex"]
REFUND_REASONS = ["damaged", "late_delivery", "duplicate_charge", "customer_request", "fraud"]

# Approximate USD-per-unit base FX rates (source -> USD). These drift daily.
BASE_FX_TO_USD = {
    "USD": "1.0000",
    "EUR": "1.0850",
    "GBP": "1.2700",
    "TRY": "0.0310",
    "JPY": "0.0067",
}

PIPELINES = [
    # (name, source_system, target_system, schedule, owner)
    ("crm_sync", "CRM API", "crm_customers", "0 1 * * *", "data-platform"),
    ("customer_mapping_pipeline", "crm_customers", "customers", "0 2 * * *", "data-platform"),
    ("orders_ingest", "Orders", "orders", "*/30 * * * *", "commerce-data"),
    ("payment_reconciliation_pipeline", "Payments", "payments", "0 3 * * *", "fin-data"),
    ("refund_pipeline", "Refunds", "refunds", "0 3 * * *", "fin-data"),
    ("fx_rate_pipeline", "FX API", "fx_rates", "0 0 * * *", "fin-data"),
    ("shipment_pipeline", "Shipments", "shipments", "0 */2 * * *", "logistics-data"),
    ("revenue_aggregation_pipeline", "orders+payments+fx", "daily_revenue_report",
     "0 5 * * *", "analytics"),
]


@dataclass(frozen=True)
class GeneratorConfig:
    """Controls dataset size and determinism."""

    seed: int = 20240601
    start: datetime = datetime(2024, 3, 1, tzinfo=timezone.utc)
    days: int = 90
    n_customers: int = 500
    n_orders: int = 20000
    # Fraction of orders that get cancelled (no payment).
    cancel_rate: float = 0.05
    # Of non-cancelled orders, fraction with a failed/pending payment.
    failed_payment_rate: float = 0.04
    pending_payment_rate: float = 0.03
    # Fraction of successful payments that receive a refund.
    refund_rate: float = 0.08
    # Fraction of orders that produce a shipment.
    shipment_rate: float = 0.85
    dataset_version: str = "v1"
    n_historical_incidents: int = 12
    logs_per_run: int = 2

    @staticmethod
    def small() -> GeneratorConfig:
        """A tiny config for fast tests."""
        return GeneratorConfig(
            n_customers=40, n_orders=600, days=20, n_historical_incidents=6
        )
