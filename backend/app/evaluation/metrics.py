"""Aggregate metric computation over per-incident evaluation results."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sklearn.metrics import f1_score

from app.evaluation.schemas import PerIncidentResult


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return float(ordered[idx])


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _escalation_metrics(results: list[PerIncidentResult]) -> dict[str, float]:
    tp = sum(1 for r in results if r.requires_human_review and r.should_escalate)
    fp = sum(1 for r in results if r.requires_human_review and not r.should_escalate)
    fn = sum(1 for r in results if not r.requires_human_review and r.should_escalate)
    tn = sum(1 for r in results if not r.requires_human_review and not r.should_escalate)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "escalation_precision": precision,
        "escalation_recall": recall,
        "escalation_f1": f1,
        "false_escalation_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "missed_escalation_rate": fn / (fn + tp) if (fn + tp) else 0.0,
    }


def _calibration(results: list[PerIncidentResult], bins: int = 10) -> dict[str, Any]:
    if not results:
        return {"brier_score": 0.0, "ece": 0.0, "curve": []}
    brier = _mean([(r.confidence - (1.0 if r.correct_top1 else 0.0)) ** 2 for r in results])
    curve = []
    ece = 0.0
    n = len(results)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [r for r in results if (lo < r.confidence <= hi) or (b == 0 and r.confidence == 0)]
        if not bucket:
            continue
        acc = _mean([1.0 if r.correct_top1 else 0.0 for r in bucket])
        conf = _mean([r.confidence for r in bucket])
        ece += len(bucket) / n * abs(acc - conf)
        curve.append({"bin": f"{lo:.1f}-{hi:.1f}", "accuracy": acc, "confidence": conf,
                      "count": len(bucket)})
    return {"brier_score": brier, "ece": ece, "curve": curve}


def _group_top1(results: list[PerIncidentResult], key) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[PerIncidentResult]] = defaultdict(list)
    for r in results:
        groups[key(r)].append(r)
    return {
        g: {"n": len(rs), "top1_accuracy": _mean([1.0 if r.correct_top1 else 0.0 for r in rs])}
        for g, rs in sorted(groups.items())
    }


def compute_metrics(results: list[PerIncidentResult]) -> dict[str, Any]:
    if not results:
        return {"n_incidents": 0}
    truth = [r.truth_code for r in results]
    leading = [r.leading_code for r in results]
    total_candidates = sum(r.num_candidates for r in results)
    total_unsupported = sum(r.unsupported_claims for r in results)

    metrics: dict[str, Any] = {
        "n_incidents": len(results),
        "root_cause_top1_accuracy": _mean([1.0 if r.correct_top1 else 0.0 for r in results]),
        "root_cause_top3_accuracy": _mean([1.0 if r.correct_top3 else 0.0 for r in results]),
        "baseline_top1_accuracy": _mean(
            [1.0 if r.baseline_correct_top1 else 0.0 for r in results]
        ),
        "classification_macro_f1": float(
            f1_score(truth, leading, average="macro", zero_division=0)
        ),
        "classification_weighted_f1": float(
            f1_score(truth, leading, average="weighted", zero_division=0)
        ),
        "unsupported_diagnosis_rate_claim_level": (
            total_unsupported / total_candidates if total_candidates else 0.0
        ),
        "unsupported_diagnosis_rate_report_level": _mean(
            [1.0 if r.unsupported_claims > 0 else 0.0 for r in results]
        ),
        "mean_latency_seconds": _mean([r.latency_seconds for r in results]),
        "p95_latency_seconds": _p95([r.latency_seconds for r in results]),
        "mean_tool_calls": _mean([float(r.tool_calls) for r in results]),
        "p95_tool_calls": _p95([float(r.tool_calls) for r in results]),
        "total_prompt_tokens": sum(r.prompt_tokens for r in results),
        "total_completion_tokens": sum(r.completion_tokens for r in results),
        "total_estimated_cost": sum(r.estimated_cost for r in results),
        **_escalation_metrics(results),
        "calibration": _calibration(results),
        "by_incident_type": _group_top1(results, lambda r: r.incident_type),
        "by_severity": _group_top1(results, lambda r: r.severity),
    }
    return metrics
