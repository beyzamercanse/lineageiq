"""Evaluation API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.db.session import session_scope
from app.evaluation.runner import run_evaluation
from app.models import EvaluationRun
from app.simulator.config import GeneratorConfig

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class EvaluationRunSummary(BaseModel):
    evaluation_run_id: str
    started_at: datetime
    completed_at: datetime | None
    dataset_version: str
    model_name: str
    metrics: dict[str, Any] | None


@router.post("/run", response_model=EvaluationRunSummary)
def run(
    per_type: int = Query(default=1, ge=1, le=8),
    small: bool = Query(default=True),
) -> EvaluationRunSummary:
    cfg = GeneratorConfig.small() if small else GeneratorConfig()
    with session_scope() as session:
        run_evaluation(session, per_type=per_type, config=cfg)
    with session_scope() as session:
        latest = session.execute(
            select(EvaluationRun).order_by(EvaluationRun.started_at.desc())
        ).scalars().first()
        return EvaluationRunSummary.model_validate(latest, from_attributes=True)


@router.get("", response_model=list[EvaluationRunSummary])
def list_runs() -> list[EvaluationRunSummary]:
    with session_scope() as session:
        rows = session.execute(
            select(EvaluationRun).order_by(EvaluationRun.started_at.desc())
        ).scalars().all()
        return [EvaluationRunSummary.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{evaluation_run_id}", response_model=EvaluationRunSummary)
def get_run(evaluation_run_id: str) -> EvaluationRunSummary:
    with session_scope() as session:
        run = session.get(EvaluationRun, evaluation_run_id)
        if run is None:
            raise NotFoundError(f"Evaluation run not found: {evaluation_run_id}")
        return EvaluationRunSummary.model_validate(run, from_attributes=True)
