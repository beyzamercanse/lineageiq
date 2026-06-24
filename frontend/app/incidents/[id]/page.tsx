"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiPost, fetcher } from "@/lib/api";
import type { IncidentDetail, InvestigationReport } from "@/types/api";

const EVIDENCE_LABEL: Record<string, string> = {
  alert: "Confirmed alert",
  sql: "SQL evidence",
  log: "Log evidence",
  lineage: "Lineage evidence",
  historical: "Historical match",
  pipeline: "Pipeline evidence",
  schema: "Schema evidence",
};

export default function IncidentDetailPage({ params }: { params: { id: string } }) {
  const { data, mutate, isLoading } = useSWR<IncidentDetail>(
    `/api/v1/incidents/${params.id}`,
    fetcher,
  );
  const [busy, setBusy] = useState(false);

  async function investigate() {
    setBusy(true);
    try {
      await apiPost<InvestigationReport>(`/api/v1/incidents/${params.id}/investigate`);
      await mutate();
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) return <div className="card">Loading…</div>;
  if (!data) return <div className="card">Incident not found.</div>;

  const report = data.agent_runs[0]?.output ?? null;

  return (
    <div>
      <h1>{data.incident.title}</h1>
      <p className="muted">
        {data.incident.incident_id} · severity {data.incident.severity} · system{" "}
        {data.incident.primary_affected_system}
      </p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <button onClick={investigate} disabled={busy}>
          {busy ? "Investigating…" : "Run AI investigation"}
        </button>
        {report && (
          <span style={{ marginLeft: "1rem" }}>
            {report.requires_human_review ? (
              <span className="badge bad">human review required</span>
            ) : (
              <span className="badge ok">auto-resolved</span>
            )}
          </span>
        )}
      </div>

      {report && (
        <>
          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3>Ranked root causes</h3>
            {report.root_cause_candidates.map((c) => (
              <div key={c.rank} style={{ marginBottom: "0.5rem" }}>
                <strong>
                  {c.rank}. {c.root_cause_code}
                </strong>{" "}
                <span className="badge">confidence {c.confidence.toFixed(2)}</span>
                <div className="muted">{c.explanation}</div>
                <div className="muted">evidence: {c.supporting_evidence_ids.length} item(s)</div>
              </div>
            ))}
            {report.requires_human_review && (
              <p className="muted">
                <strong>Human review:</strong> {report.human_review_reason}
              </p>
            )}
            {report.unsupported_claims.length > 0 && (
              <p>
                <span className="badge bad">unsupported claims</span>{" "}
                {report.unsupported_claims.join("; ")}
              </p>
            )}
          </div>

          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3>Impact</h3>
            <div>
              Systems:{" "}
              {report.impacted_systems.map((s) => (
                <span key={s} className="badge" style={{ marginRight: "0.3rem" }}>
                  {s}
                </span>
              ))}
            </div>
            <div style={{ marginTop: "0.4rem" }}>
              Reports:{" "}
              {report.impacted_reports.map((s) => (
                <span key={s} className="badge bad" style={{ marginRight: "0.3rem" }}>
                  {s}
                </span>
              ))}
            </div>
          </div>

          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3>Recommended remediation (requires approval)</h3>
            {report.remediation_recommendations.map((r, i) => (
              <div key={i} className="muted">
                • {r.action} — {r.target_system} (risk {r.risk})
              </div>
            ))}
          </div>
        </>
      )}

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>Evidence ({data.evidence.length})</h3>
        {data.evidence.map((e) => (
          <div key={e.evidence_id} style={{ borderBottom: "1px solid var(--border)", padding: "0.4rem 0" }}>
            <span className="badge">{EVIDENCE_LABEL[e.evidence_type] ?? e.evidence_type}</span>{" "}
            <span className="muted">{e.evidence_id}</span>
            <div>{e.summary}</div>
          </div>
        ))}
      </div>

      {data.ground_truth && (
        <div className="card">
          <h3>Ground truth (synthetic)</h3>
          <p className="muted">
            Injected root cause: <strong>{data.ground_truth.root_cause_code}</strong>
            {report &&
              report.root_cause_candidates[0]?.root_cause_code ===
                data.ground_truth.root_cause_code && (
                <span className="badge ok" style={{ marginLeft: "0.5rem" }}>
                  diagnosis correct
                </span>
              )}
          </p>
        </div>
      )}
    </div>
  );
}
