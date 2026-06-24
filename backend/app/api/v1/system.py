"""Health and system-status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.db.session import get_db
from app.schemas.system import HealthResponse, SystemStatusResponse
from app.services.system_service import get_system_status

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — does not touch the database."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/system/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db)) -> SystemStatusResponse:
    """Readiness/status — reports DB reachability and table counts."""
    return get_system_status(db)
