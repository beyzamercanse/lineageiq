"""Automated, LLM-free investigation baseline.

Runs the deterministic control checklist and ranks root causes by detector signal. Used to compare
the agent against a no-LLM baseline.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.taxonomy import RootCauseCode
from app.detection.detectors import ALL_DETECTORS, run_all_detectors


@dataclass
class BaselineResult:
    leading_code: str
    ranked_codes: list[str]
    query_count: int
    latency_seconds: float


def run_baseline(session: Session) -> BaselineResult:
    start = time.perf_counter()
    alerts = run_all_detectors(session)
    counts = Counter(
        a.suspected_root_cause.value
        for a in alerts
        if a.suspected_root_cause != RootCauseCode.UNKNOWN
    )
    ranked = [code for code, _ in counts.most_common()]
    leading = ranked[0] if ranked else RootCauseCode.UNKNOWN.value
    return BaselineResult(
        leading_code=leading,
        ranked_codes=ranked,
        query_count=len(ALL_DETECTORS),
        latency_seconds=time.perf_counter() - start,
    )
