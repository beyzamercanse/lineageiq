"""System / health response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class SystemStatusResponse(BaseModel):
    status: str
    version: str
    environment: str
    database_backend: str
    database_reachable: bool
    llm_provider: str
    seed: int
    table_counts: dict[str, int]
