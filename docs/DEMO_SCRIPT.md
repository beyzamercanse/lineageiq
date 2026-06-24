# LineageIQ — Demo Script (Stale FX Rate)

The primary end-to-end demo and CI fixture.

## One command
```bash
make demo
```
This resets the DB, seeds the clean AtlasCommerce dataset, generates incident manifests, injects
the stale-FX-rate incident, runs detection, creates the incident, and runs the investigation with
the deterministic FakeLLM.

## Narrative
1. The FX API fails to update EUR/USD for a specific date.
2. The FX pipeline completes reusing yesterday's rate (low row count, warning logs).
3. Orders and payments remain operational.
4. The daily revenue report uses the stale rate.
5. Reported USD revenue deviates from the clean expected result.
6. A reconciliation detector raises an alert → incident created.
7. The agent queries the affected report.
8. The agent compares relevant FX rates.
9. The agent inspects FX pipeline logs and runs.
10. The lineage graph connects the FX source to the revenue report.
11. A similar historical incident is retrieved.
12. The final report ranks `STALE_FX_RATE` first.
13. The report cites SQL, pipeline, log, and lineage evidence.
14. The agent recommends refreshing FX data and regenerating affected reports.
15. The agent states remediation requires human approval.

## In the UI
- Operations overview → see the new incident.
- Incident detail → ranked candidates, evidence cards, agent trace, lineage impact, human-review.
- Lineage explorer → trace FX source → daily_revenue_report → executive dashboard.
- Evaluation dashboard → run/inspect metrics.
