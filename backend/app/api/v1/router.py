"""Aggregates all v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import lineage, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(lineage.router)
