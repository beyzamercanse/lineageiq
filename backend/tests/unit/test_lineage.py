from __future__ import annotations

import pytest

from app.lineage.graph_config import build_atlas_lineage
from app.lineage.types import NodeType


@pytest.fixture
def store():
    return build_atlas_lineage()


@pytest.mark.unit
def test_downstream_of_fx_reaches_report_and_dashboard(store):
    result = store.downstream("fx_rates")
    ids = {n.id for n in result.nodes}
    assert "daily_revenue_report" in ids
    assert "executive_revenue_dashboard" in ids
    assert "daily_revenue_report" in result.affected_assets
    assert "executive_revenue_dashboard" in result.affected_assets


@pytest.mark.unit
def test_upstream_of_report_reaches_sources(store):
    result = store.upstream("daily_revenue_report")
    ids = {n.id for n in result.nodes}
    assert {"fx_rates", "orders", "payments", "refunds"} <= ids
    # FX source API is upstream of the report.
    assert "fx_api" in ids


@pytest.mark.unit
def test_shortest_path_fx_api_to_dashboard(store):
    path = store.shortest_path("fx_api", "executive_revenue_dashboard")
    assert path is not None
    assert path[0] == "fx_api"
    assert path[-1] == "executive_revenue_dashboard"
    assert "fx_rates" in path
    assert "daily_revenue_report" in path


@pytest.mark.unit
def test_impact_lists_only_business_assets(store):
    result = store.impact("fx_rates")
    for asset_id in result.affected_assets:
        node = store.get_node(asset_id)
        assert node.type in (NodeType.REPORT, NodeType.DASHBOARD, NodeType.BUSINESS_METRIC)


@pytest.mark.unit
def test_unknown_node_raises(store):
    with pytest.raises(KeyError):
        store.downstream("does_not_exist")


@pytest.mark.unit
def test_serialization_roundtrips_counts(store):
    data = store.to_dict()
    assert len(data["nodes"]) == len(store.all_nodes())
    assert len(data["edges"]) == len(store.all_edges())
