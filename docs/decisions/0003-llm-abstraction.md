# ADR-0003: Provider-independent LLM interface with deterministic FakeLLM

## Status
Accepted

## Context
The agent needs an LLM, but tests/CI must run without a paid API, and we must not lock to one
commercial provider.

## Decision
Define an `LLMClient` protocol (`complete`, `complete_structured`, tool-calling, token/cost
tracking). Provide `OpenAICompatibleLLM` (real, configurable base URL + model) and `FakeLLM`
(deterministic, scripted). Configure provider via env.

## Consequences
- Tests and the stale-FX CI fixture run fully offline and deterministically.
- Swapping providers is a config change, not a code change.
