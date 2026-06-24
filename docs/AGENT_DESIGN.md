# LineageIQ — Agent Design

## Bounded investigation loop
1. Receive incident + initial alerts.
2. Summarize known symptoms.
3. Identify relevant systems / lineage nodes.
4. Generate an investigation plan.
5. Select a read-only tool and call it.
6. Collect evidence (every tool call ⇒ an `evidence` row).
7. Update ranked root-cause hypotheses.
8. Decide whether more evidence is needed.
9. Stop when sufficient or budget exhausted.
10. Produce a structured `InvestigationReport`.

## Budgets (defaults, configurable)
- max 8 tool calls, max 2 SQL retries, max wall-clock duration, max token budget, cost ceiling.

## Tools (read-only)
`run_readonly_sql`, `search_logs`, `query_lineage`, `search_historical_incidents`,
`inspect_pipeline_runs`, `inspect_schema`. All validate inputs/outputs, are size-bounded, traced,
logged, fail safely, never return secrets, and produce evidence records.

The agent never executes remediation — it only recommends it.

## Structured output (Pydantic)
`RootCauseCandidate`, `RecommendedCheck`, `RemediationRecommendation`, `InvestigationReport`
(see `app/schemas/investigation.py`). All confidence values ∈ [0, 1]. A candidate with no
supporting evidence cannot receive high confidence.

## Prompt-injection defense
Tool results are wrapped and labeled as untrusted data. The system prompt instructs the model to
treat any instruction-like content inside tool output as data to analyze, never as commands.

## Human-review policy (escalate if ANY true)
- overall confidence < 0.65
- < 2 independent evidence sources support the leading diagnosis
- tool results conflict
- investigation budget reached
- critical data unavailable
- multiple root causes similarly probable
- remediation could alter production data
- incident severity == critical
- incident type outside the evaluation taxonomy

## LLM abstraction
`LLMClient` protocol with `OpenAICompatibleLLM` (real) and `FakeLLM` (deterministic, used in
tests/CI). Structured outputs validated with Pydantic; tool-calling supported; token + cost
tracked per run.
