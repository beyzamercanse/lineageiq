from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.errors import ToolSafetyError
from app.lineage.graph_config import build_atlas_lineage
from app.models import Base
from app.tools.base import ToolContext
from app.tools.sql_tool import RunReadonlySqlTool


def _ctx() -> ToolContext:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return ToolContext(
        session=Session(engine), incident_id="INC-x", lineage=build_atlas_lineage(),
    )


@pytest.mark.security
@pytest.mark.parametrize("query", [
    "INSERT INTO orders (order_id) VALUES ('x')",
    "UPDATE orders SET gross_amount = 0",
    "DELETE FROM orders",
    "DROP TABLE orders",
])
def test_agent_sql_tool_rejects_writes(query):
    tool = RunReadonlySqlTool()
    with pytest.raises(ToolSafetyError):
        tool.run(_ctx(), query=query, reason="attempted write")
