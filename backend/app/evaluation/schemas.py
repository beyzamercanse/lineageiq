"""Evaluation result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerIncidentResult:
    manifest_id: str
    incident_type: str
    severity: str
    truth_code: str
    leading_code: str
    candidate_codes: list[str]
    confidence: float
    correct_top1: bool
    correct_top3: bool
    requires_human_review: bool
    should_escalate: bool
    num_candidates: int
    unsupported_claims: int
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float
    latency_seconds: float
    baseline_leading_code: str
    baseline_correct_top1: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EvaluationOutput:
    metrics: dict[str, Any]
    per_incident: list[PerIncidentResult] = field(default_factory=list)
