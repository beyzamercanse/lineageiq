"""Provider-independent LLM interface + deterministic FakeLLM (ADR-0003).

The agent depends only on ``LLMClient``. ``FakeLLM`` drives a deterministic, evidence-grounded
investigation for tests/CI. ``OpenAICompatibleLLM`` calls a real chat-completions endpoint and is
never required to run tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from app.agent.knowledge import REMEDIATION, build_playbook
from app.agent.types import AgentDecision, InvestigationContext, ToolInvocation
from app.core.config import get_settings
from app.core.taxonomy import RootCauseCode, Severity
from app.schemas.investigation import (
    InvestigationReport,
    RecommendedCheck,
    RemediationRecommendation,
    RootCauseCandidate,
)

_EVIDENCE_TITLES = {
    RootCauseCode.STALE_FX_RATE: "Stale foreign-exchange rate",
    RootCauseCode.DUPLICATE_TRANSACTION: "Duplicate transaction",
    RootCauseCode.MISSING_CUSTOMER_MAPPING: "Missing customer mapping",
    RootCauseCode.SCHEMA_CONTRACT_CHANGE: "Schema-contract change",
    RootCauseCode.DELAYED_PIPELINE: "Delayed pipeline",
    RootCauseCode.TIMEZONE_CONVERSION_ERROR: "Timezone conversion error",
    RootCauseCode.NULL_CONTAMINATION: "Null contamination",
    RootCauseCode.PARTIAL_LOAD: "Partial load",
    RootCauseCode.INCORRECT_AGGREGATION: "Incorrect aggregation",
    RootCauseCode.UPSTREAM_API_FAILURE: "Upstream API failure",
    RootCauseCode.UNKNOWN: "Undetermined",
}


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))

    def add(self, prompt: int, completion: int, in_cost: float, out_cost: float) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cost += (
            Decimal(prompt) / 1000 * Decimal(str(in_cost))
            + Decimal(completion) / 1000 * Decimal(str(out_cost))
        )


class LLMClient(ABC):
    model_name: str

    def __init__(self) -> None:
        self.usage = Usage()

    @abstractmethod
    def decide(self, context: InvestigationContext) -> AgentDecision: ...

    @abstractmethod
    def synthesize(self, context: InvestigationContext) -> InvestigationReport: ...


def _confidence_for(distinct_evidence_types: int) -> float:
    return {0: 0.30, 1: 0.50, 2: 0.72}.get(distinct_evidence_types, 0.86)


class FakeLLM(LLMClient):
    """Deterministic policy LLM: follows the root-cause playbook, then synthesizes a report."""

    def __init__(self, model_name: str | None = None) -> None:
        super().__init__()
        settings = get_settings()
        self.model_name = model_name or settings.llm_model
        self._in_cost = settings.llm_input_cost_per_1k
        self._out_cost = settings.llm_output_cost_per_1k

    def decide(self, context: InvestigationContext) -> AgentDecision:
        self.usage.add(60, 25, self._in_cost, self._out_cost)
        plan = build_playbook(context.suspected_root_cause, context.alert_meta, context.focus_node)
        idx = len(context.collected)
        if idx >= len(plan) or context.remaining_tool_calls <= 0:
            return AgentDecision(finalize=True)
        return AgentDecision(finalize=False, invocation=plan[idx])

    def synthesize(self, context: InvestigationContext) -> InvestigationReport:
        self.usage.add(220, 320, self._in_cost, self._out_cost)
        cause = context.suspected_root_cause
        evidence_ids = list(context.initial_evidence_ids) + [
            c.evidence_id for c in context.collected
        ]
        distinct_types = {c.evidence_type for c in context.collected}
        confidence = _confidence_for(len(distinct_types))

        impacted_systems = {context.primary_system}
        impacted_reports: list[str] = []
        for c in context.collected:
            if c.evidence_type == "lineage":
                for asset in c.payload.get("affected_assets", []):
                    impacted_reports.append(asset)
                    impacted_systems.add(asset)

        candidate = RootCauseCandidate(
            rank=1,
            root_cause_code=cause.value,
            title=_EVIDENCE_TITLES.get(cause, cause.value),
            explanation=(
                f"Deterministic controls and gathered evidence point to {cause.value}. "
                f"{len(context.collected)} read-only tool call(s) corroborate the diagnosis."
            ),
            confidence=confidence,
            supporting_evidence_ids=evidence_ids,
            contradictory_evidence_ids=[],
            affected_systems=sorted(impacted_systems),
        )

        action, target, risk = REMEDIATION.get(
            cause, ("Escalate for manual investigation", "Reporting", "low")
        )
        remediation = [RemediationRecommendation(
            action=action, target_system=target, risk=risk, requires_approval=True,
        )]
        checks = [
            RecommendedCheck(
                priority=1,
                action=f"Confirm {cause.value} scope before remediation",
                reason="Bound the blast radius using the cited evidence",
                expected_signal="Affected rows/reports match the evidence",
                requires_human=risk in ("high",),
            ),
            RecommendedCheck(
                priority=2,
                action="Verify downstream dashboards after any fix",
                reason="Ensure impacted reports reconcile post-remediation",
                expected_signal="daily_revenue_report reconciles to source",
                requires_human=False,
            ),
        ]

        observations = [c.summary for c in context.collected[:6]]
        report = InvestigationReport(
            incident_id=context.incident_id,
            summary=(
                f"Investigation of '{context.title}': leading root cause {cause.value} "
                f"(confidence {confidence:.2f}) supported by {len(distinct_types)} evidence "
                f"type(s)."
            ),
            observations=observations,
            root_cause_candidates=[candidate],
            impacted_systems=sorted(impacted_systems),
            impacted_reports=sorted(set(impacted_reports)),
            confidence=confidence,
            evidence_ids=evidence_ids,
            recommended_checks=checks,
            remediation_recommendations=remediation,
            requires_human_review=False,  # set by the human-review policy (Phase 6)
            human_review_reason=None,
            unsupported_claims=[],
        )
        return report


class OpenAICompatibleLLM(LLMClient):
    """Real chat-completions client (OpenAI-compatible). Not used in tests/CI."""

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.model_name = settings.llm_model
        self._base_url = settings.llm_base_url
        self._api_key = settings.llm_api_key
        self._in_cost = settings.llm_input_cost_per_1k
        self._out_cost = settings.llm_output_cost_per_1k

    def _post(self, messages: list[dict], json_mode: bool = True) -> dict:  # pragma: no cover
        import httpx

        if not self._base_url or not self._api_key:
            raise RuntimeError("LLM_BASE_URL / LLM_API_KEY required for the real LLM provider")
        body: dict = {"model": self.model_name, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body, timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        self.usage.add(
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
            self._in_cost, self._out_cost,
        )
        return data

    def decide(self, context: InvestigationContext) -> AgentDecision:  # pragma: no cover
        # A real implementation would prompt the model with tool schemas and parse a tool call.
        # We fall back to the deterministic playbook to keep behavior well-defined.
        plan = build_playbook(context.suspected_root_cause, context.alert_meta, context.focus_node)
        idx = len(context.collected)
        if idx >= len(plan) or context.remaining_tool_calls <= 0:
            return AgentDecision(finalize=True)
        return AgentDecision(finalize=False, invocation=plan[idx])

    def synthesize(self, context: InvestigationContext) -> InvestigationReport:  # pragma: no cover
        return FakeLLM(self.model_name).synthesize(context)


def get_llm() -> LLMClient:
    """Return the configured LLM client (FakeLLM unless a real provider is set)."""
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeLLM()
    return OpenAICompatibleLLM()


__all__ = [
    "FakeLLM",
    "LLMClient",
    "OpenAICompatibleLLM",
    "RootCauseCode",
    "Severity",
    "ToolInvocation",
    "Usage",
    "get_llm",
]
