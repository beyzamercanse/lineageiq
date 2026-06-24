"""Detection DTOs. A standardized Alert object every detector emits."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.taxonomy import RootCauseCode, Severity


class AlertDTO(BaseModel):
    """A standardized alert produced by a deterministic detector."""

    detector_name: str
    entity_type: str
    entity_id: str
    metric_name: str
    observed_value: str | None = None
    expected_value: str | None = None
    anomaly_score: float | None = None
    severity: Severity = Severity.MEDIUM
    suspected_root_cause: RootCauseCode = RootCauseCode.UNKNOWN
    detected_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
