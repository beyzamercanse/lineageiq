# LineageIQ — Evaluation Methodology

## Runner
For each incident: restore/regenerate clean data → inject incident → run detectors → create
incident → run investigation agent (FakeLLM in CI) → validate report → compare with ground truth
→ save per-incident result → aggregate.

Each incident is evaluated in isolation against a freshly restored clean baseline so runs are
fully repeatable.

## Metrics
- **Root-cause top-1 accuracy** — leading predicted code == ground-truth code.
- **Root-cause top-3 accuracy** — ground-truth code within first 3 candidates.
- **Incident classification F1** — macro and weighted.
- **Unsupported diagnosis rate** — claim-level (claims w/o valid evidence / total claims) and
  report-level.
- **Human-review routing** — escalation precision, recall, F1, false-escalation rate,
  missed-escalation rate.
- **Performance** — total/tool/LLM latency, mean & p95 tool-call count, prompt/completion tokens,
  estimated API cost.
- **Confidence calibration** — Brier score, calibration-curve data, ECE where practical.
- **Breakdowns** — by incident type, severity, affected system, #evidence sources, should-escalate.

## Outputs
PostgreSQL (`evaluation_runs`), JSON, CSV, and a Markdown report under `data/evaluation/`.
README results are generated, never hand-written.

## Baselines
- **Automated baseline:** deterministic, LLM-free checklist investigator for comparison.
- **Manual benchmark:** `data/evaluation/manual_benchmark_template.csv` for real human timings.
  No manual-time improvement is claimed until real measurements are entered.

## Severity labels (synthetic)
Severity is derived from affected-record count, monetary exposure, #customers, #downstream
reports, duration, recurrence, regulatory impact, and detection confidence. The mapping is
documented in `app/detection/severity.py`.
