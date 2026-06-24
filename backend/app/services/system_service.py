"""System status service: reports DB reachability and table counts."""

from __future__ import annotations

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.models import (
    Alert,
    Customer,
    Evidence,
    FxRate,
    Incident,
    Order,
    Payment,
    PipelineRun,
    Refund,
)
from app.schemas.system import SystemStatusResponse

# (label -> model) for the status table-count panel.
_COUNT_MODELS = {
    "customers": Customer,
    "orders": Order,
    "payments": Payment,
    "refunds": Refund,
    "fx_rates": FxRate,
    "pipeline_runs": PipelineRun,
    "alerts": Alert,
    "incidents": Incident,
    "evidence": Evidence,
}


def get_system_status(session: Session) -> SystemStatusResponse:
    settings = get_settings()
    reachable = True
    counts: dict[str, int] = {}
    engine = session.get_bind().engine
    backend = engine.url.get_backend_name()
    try:
        existing = set(inspect(engine).get_table_names())
        for label, model in _COUNT_MODELS.items():
            if model.__tablename__ in existing:
                counts[label] = session.scalar(select(func.count()).select_from(model)) or 0
            else:
                counts[label] = 0
    except Exception:
        # Status endpoint must never raise; report degraded instead.
        reachable = False

    return SystemStatusResponse(
        status="ok" if reachable else "degraded",
        version=__version__,
        environment=settings.lineageiq_env,
        database_backend=backend,
        database_reachable=reachable,
        llm_provider=settings.llm_provider,
        seed=settings.random_seed,
        table_counts=counts,
    )
