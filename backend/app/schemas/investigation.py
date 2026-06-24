"""Structured investigation-report schemas (the agent's typed output).

Confidence values are constrained to [0, 1]. A candidate without supporting evidence cannot earn
high confidence (enforced by the validator in Phase 6).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RootCauseCandidate(BaseModel):
    rank: int
    root_cause_code: str
    title: str
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    affected_systems: list[str] = Field(default_factory=list)


class RecommendedCheck(BaseModel):
    priority: int
    action: str
    reason: str
    expected_signal: str
    requires_human: bool = False


class RemediationRecommendation(BaseModel):
    action: str
    target_system: str
    risk: str
    requires_approval: bool = True


class InvestigationReport(BaseModel):
    incident_id: str
    summary: str
    observations: list[str] = Field(default_factory=list)
    root_cause_candidates: list[RootCauseCandidate] = Field(default_factory=list)
    impacted_systems: list[str] = Field(default_factory=list)
    impacted_reports: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_ids: list[str] = Field(default_factory=list)
    recommended_checks: list[RecommendedCheck] = Field(default_factory=list)
    remediation_recommendations: list[RemediationRecommendation] = Field(default_factory=list)
    requires_human_review: bool = False
    human_review_reason: str | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
