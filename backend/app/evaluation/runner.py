"""Evaluation runner.

For each incident (isolated against a freshly restored clean baseline): inject -> detect ->
create incident -> run the automated baseline -> run the agent investigation -> validate ->
compare to ground truth. Aggregates metrics and writes JSON/CSV/Markdown + an EvaluationRun row.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import FakeLLM, LLMClient
from app.agent.orchestrator import investigate_incident
from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import get_logger
from app.detection.detectors import run_all_detectors
from app.evaluation.baseline import run_baseline
from app.evaluation.metrics import compute_metrics
from app.evaluation.schemas import EvaluationOutput, PerIncidentResult
from app.incidents.restore import restore_clean_baseline
from app.incidents.service import create_incident_from_alerts, generate_manifests, inject_manifest
from app.models import AgentRun, EvaluationRun
from app.simulator.config import GeneratorConfig

log = get_logger(__name__)

REPORT_DIR = PROJECT_ROOT / "data" / "evaluation" / "runs"
SUMMARY_PATH = PROJECT_ROOT / "data" / "evaluation" / "latest_report.md"


def run_evaluation(
    session: Session,
    *,
    per_type: int = 1,
    config: GeneratorConfig | None = None,
    llm_factory: Callable[[], LLMClient] | None = None,
    dataset_version: str = "v1",
    persist: bool = True,
) -> EvaluationOutput:
    config = config or GeneratorConfig(seed=get_settings().random_seed)
    llm_factory = llm_factory or (lambda: FakeLLM())

    restore_clean_baseline(session, config)
    session.flush()
    manifests = generate_manifests(session, seed=config.seed, per_type=per_type, save=False)

    results: list[PerIncidentResult] = []
    for m in manifests:
        restore_clean_baseline(session, config)
        session.flush()
        inject_manifest(session, m)
        session.flush()

        baseline = run_baseline(session)
        alerts = run_all_detectors(session)
        incident = create_incident_from_alerts(session, alerts, manifest=m)

        t0 = time.perf_counter()
        report = investigate_incident(session, incident.incident_id, llm=llm_factory())
        latency = time.perf_counter() - t0

        run = session.execute(
            select(AgentRun).where(AgentRun.incident_id == incident.incident_id)
            .order_by(AgentRun.started_at.desc())
        ).scalars().first()

        truth = m.root_cause_code.value
        candidate_codes = [c.root_cause_code for c in report.root_cause_candidates]
        leading = candidate_codes[0] if candidate_codes else "UNKNOWN"
        results.append(PerIncidentResult(
            manifest_id=m.manifest_id,
            incident_type=m.incident_type.value,
            severity=m.severity.value,
            truth_code=truth,
            leading_code=leading,
            candidate_codes=candidate_codes,
            confidence=report.confidence,
            correct_top1=leading == truth,
            correct_top3=truth in candidate_codes[:3],
            requires_human_review=report.requires_human_review,
            should_escalate=m.should_escalate,
            num_candidates=len(report.root_cause_candidates),
            unsupported_claims=len(report.unsupported_claims),
            tool_calls=run.tool_call_count if run else 0,
            prompt_tokens=run.prompt_tokens if run else 0,
            completion_tokens=run.completion_tokens if run else 0,
            estimated_cost=float(run.estimated_cost) if run else 0.0,
            latency_seconds=latency,
            baseline_leading_code=baseline.leading_code,
            baseline_correct_top1=baseline.leading_code == truth,
        ))

    metrics = compute_metrics(results)
    run_id = f"EVAL-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    report_path = None
    if persist:
        report_path = _write_reports(run_id, metrics, results, dataset_version)
        restore_clean_baseline(session, config)
        session.flush()
        session.add(EvaluationRun(
            evaluation_run_id=run_id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            dataset_version=dataset_version,
            model_name=llm_factory().model_name,
            configuration={"per_type": per_type, "seed": config.seed},
            metrics=metrics,
            report_path=report_path,
        ))
        session.flush()
        log.info("evaluation_complete", extra={"run_id": run_id, "metrics": {
            k: metrics[k] for k in ("n_incidents", "root_cause_top1_accuracy") if k in metrics
        }})

    return EvaluationOutput(metrics=metrics, per_incident=results)


def _write_reports(
    run_id: str, metrics: dict[str, Any], results: list[PerIncidentResult], dataset_version: str
) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{run_id}.json").write_text(json.dumps(
        {"run_id": run_id, "metrics": metrics,
         "per_incident": [r.to_dict() for r in results]}, indent=2, default=str))

    csv_path = REPORT_DIR / f"{run_id}.csv"
    if results:
        with csv_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].to_dict().keys()))
            writer.writeheader()
            for r in results:
                writer.writerow(r.to_dict())

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(_markdown(run_id, metrics, dataset_version))
    return str(REPORT_DIR / f"{run_id}.json")


def _markdown(run_id: str, m: dict[str, Any], dataset_version: str) -> str:
    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    lines = [
        f"# LineageIQ Evaluation Report — {run_id}",
        "",
        f"_Generated by the evaluation runner. Dataset {dataset_version}. "
        f"{m.get('n_incidents', 0)} incidents (FakeLLM, deterministic)._",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Root-cause top-1 accuracy | {pct(m['root_cause_top1_accuracy'])} |",
        f"| Root-cause top-3 accuracy | {pct(m['root_cause_top3_accuracy'])} |",
        f"| Automated-baseline top-1 | {pct(m['baseline_top1_accuracy'])} |",
        f"| Incident classification macro-F1 | {m['classification_macro_f1']:.3f} |",
        f"| Incident classification weighted-F1 | {m['classification_weighted_f1']:.3f} |",
        f"| Unsupported-diagnosis rate (claim) | "
        f"{pct(m['unsupported_diagnosis_rate_claim_level'])} |",
        f"| Unsupported-diagnosis rate (report) | "
        f"{pct(m['unsupported_diagnosis_rate_report_level'])} |",
        f"| Escalation precision | {pct(m['escalation_precision'])} |",
        f"| Escalation recall | {pct(m['escalation_recall'])} |",
        f"| Escalation F1 | {pct(m['escalation_f1'])} |",
        f"| False-escalation rate | {pct(m['false_escalation_rate'])} |",
        f"| Missed-escalation rate | {pct(m['missed_escalation_rate'])} |",
        f"| Mean diagnosis latency | {m['mean_latency_seconds']:.3f}s |",
        f"| p95 diagnosis latency | {m['p95_latency_seconds']:.3f}s |",
        f"| Mean tool calls | {m['mean_tool_calls']:.2f} |",
        f"| Prompt / completion tokens | "
        f"{m['total_prompt_tokens']} / {m['total_completion_tokens']} |",
        f"| Estimated cost (USD) | {m['total_estimated_cost']:.4f} |",
        f"| Brier score | {m['calibration']['brier_score']:.4f} |",
        f"| Expected calibration error | {m['calibration']['ece']:.4f} |",
        "",
        "## Top-1 accuracy by incident type",
        "",
        "| Incident type | N | Top-1 |",
        "| --- | --- | --- |",
    ]
    for itype, stats in m["by_incident_type"].items():
        lines.append(f"| {itype} | {stats['n']} | {pct(stats['top1_accuracy'])} |")
    lines.append("")
    return "\n".join(lines)
