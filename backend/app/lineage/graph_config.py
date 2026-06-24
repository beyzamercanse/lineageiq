"""AtlasCommerce lineage graph definition (version-controlled config).

Edges point in the direction of data flow (source -> consumer), so downstream traversal answers
"what does this feed?" and upstream answers "what feeds this?".
"""

from __future__ import annotations

from app.core.taxonomy import RootCauseCode
from app.lineage.store import LineageStore, NetworkXLineageStore
from app.lineage.types import EdgeType, LineageEdge, LineageNode, NodeType

# (id, type, label, metadata)
_NODES: list[tuple[str, NodeType, str, dict]] = [
    # External APIs / source systems
    ("crm_api", NodeType.API, "CRM API", {"team": "crm"}),
    ("fx_api", NodeType.API, "FX Rates API", {"provider": "ecb_proxy"}),
    ("payment_provider_api", NodeType.API, "Payment Provider API", {}),
    ("orders_system", NodeType.SYSTEM, "Orders System", {}),
    ("shipments_system", NodeType.SYSTEM, "Shipments System", {}),
    # Database
    ("atlas_postgres", NodeType.DATABASE, "AtlasCommerce Postgres", {}),
    # Tables
    ("crm_customers", NodeType.TABLE, "crm_customers", {}),
    ("customers", NodeType.TABLE, "customers", {}),
    ("customer_limits", NodeType.TABLE, "customer_limits", {}),
    ("orders", NodeType.TABLE, "orders", {}),
    ("payments", NodeType.TABLE, "payments", {}),
    ("refunds", NodeType.TABLE, "refunds", {}),
    ("fx_rates", NodeType.TABLE, "fx_rates", {}),
    ("shipments", NodeType.TABLE, "shipments", {}),
    ("staging_records", NodeType.TABLE, "staging_records", {"zone": "staging"}),
    # Pipelines
    ("crm_sync", NodeType.PIPELINE, "crm_sync", {}),
    ("customer_mapping_pipeline", NodeType.PIPELINE, "customer_mapping_pipeline", {}),
    ("orders_ingest", NodeType.PIPELINE, "orders_ingest", {}),
    ("payment_reconciliation_pipeline", NodeType.PIPELINE, "payment_reconciliation_pipeline", {}),
    ("refund_pipeline", NodeType.PIPELINE, "refund_pipeline", {}),
    ("fx_rate_pipeline", NodeType.PIPELINE, "fx_rate_pipeline", {}),
    ("shipment_pipeline", NodeType.PIPELINE, "shipment_pipeline", {}),
    ("revenue_aggregation_pipeline", NodeType.PIPELINE, "revenue_aggregation_pipeline", {}),
    # Reports / dashboards / metrics
    ("daily_revenue_report", NodeType.REPORT, "daily_revenue_report", {}),
    ("executive_revenue_dashboard", NodeType.DASHBOARD, "Executive Revenue Dashboard", {}),
    ("finance_reconciliation_dashboard", NodeType.DASHBOARD,
     "Finance Reconciliation Dashboard", {}),
    ("usd_net_revenue", NodeType.BUSINESS_METRIC, "USD Net Revenue", {}),
    ("refund_rate_metric", NodeType.BUSINESS_METRIC, "Refund Rate", {}),
]

# (source, target, type)
_EDGES: list[tuple[str, str, EdgeType]] = [
    # CRM -> customers
    ("crm_api", "crm_sync", EdgeType.CALLS),
    ("crm_sync", "crm_customers", EdgeType.WRITES_TO),
    ("crm_customers", "customer_mapping_pipeline", EdgeType.READS_FROM),
    ("customer_mapping_pipeline", "customers", EdgeType.WRITES_TO),
    ("customers", "customer_limits", EdgeType.MAPS_TO),
    # Orders
    ("orders_system", "orders_ingest", EdgeType.CALLS),
    ("orders_ingest", "staging_records", EdgeType.WRITES_TO),
    ("staging_records", "orders", EdgeType.TRANSFORMS),
    ("customers", "orders", EdgeType.DEPENDS_ON),
    # Payments
    ("payment_provider_api", "payment_reconciliation_pipeline", EdgeType.CALLS),
    ("orders", "payment_reconciliation_pipeline", EdgeType.READS_FROM),
    ("payment_reconciliation_pipeline", "payments", EdgeType.WRITES_TO),
    # Refunds
    ("payments", "refund_pipeline", EdgeType.READS_FROM),
    ("refund_pipeline", "refunds", EdgeType.WRITES_TO),
    # FX
    ("fx_api", "fx_rate_pipeline", EdgeType.CALLS),
    ("fx_rate_pipeline", "fx_rates", EdgeType.WRITES_TO),
    # Shipments
    ("shipments_system", "shipment_pipeline", EdgeType.CALLS),
    ("orders", "shipment_pipeline", EdgeType.READS_FROM),
    ("shipment_pipeline", "shipments", EdgeType.WRITES_TO),
    # Revenue aggregation -> report -> dashboards/metrics
    ("orders", "revenue_aggregation_pipeline", EdgeType.AGGREGATES_INTO),
    ("payments", "revenue_aggregation_pipeline", EdgeType.AGGREGATES_INTO),
    ("refunds", "revenue_aggregation_pipeline", EdgeType.AGGREGATES_INTO),
    ("fx_rates", "revenue_aggregation_pipeline", EdgeType.AGGREGATES_INTO),
    ("revenue_aggregation_pipeline", "daily_revenue_report", EdgeType.WRITES_TO),
    ("daily_revenue_report", "executive_revenue_dashboard", EdgeType.PUBLISHES),
    ("daily_revenue_report", "finance_reconciliation_dashboard", EdgeType.PUBLISHES),
    ("daily_revenue_report", "usd_net_revenue", EdgeType.AGGREGATES_INTO),
    ("refunds", "refund_rate_metric", EdgeType.AGGREGATES_INTO),
]


def build_atlas_lineage() -> LineageStore:
    """Build and return the AtlasCommerce lineage graph."""
    store = NetworkXLineageStore()
    for node_id, node_type, label, meta in _NODES:
        store.add_node(LineageNode(id=node_id, type=node_type, label=label, metadata=meta))
    for source, target, edge_type in _EDGES:
        store.add_edge(LineageEdge(source=source, target=target, type=edge_type))
    return store


# Where the agent should start a lineage query for each root cause (Phase 5 uses this).
ROOT_CAUSE_FOCUS_NODE: dict[RootCauseCode, str] = {
    RootCauseCode.DUPLICATE_TRANSACTION: "payments",
    RootCauseCode.STALE_FX_RATE: "fx_rates",
    RootCauseCode.MISSING_CUSTOMER_MAPPING: "customers",
    RootCauseCode.SCHEMA_CONTRACT_CHANGE: "orders",
    RootCauseCode.DELAYED_PIPELINE: "revenue_aggregation_pipeline",
    RootCauseCode.TIMEZONE_CONVERSION_ERROR: "orders",
    RootCauseCode.NULL_CONTAMINATION: "staging_records",
    RootCauseCode.PARTIAL_LOAD: "orders",
    RootCauseCode.INCORRECT_AGGREGATION: "revenue_aggregation_pipeline",
    RootCauseCode.UPSTREAM_API_FAILURE: "payment_provider_api",
    RootCauseCode.UNKNOWN: "daily_revenue_report",
}
