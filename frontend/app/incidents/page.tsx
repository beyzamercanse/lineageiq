"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { IncidentSummary } from "@/types/api";

const SEVERITIES = ["all", "critical", "high", "medium", "low"];

export default function IncidentsPage() {
  const { data, error, isLoading } = useSWR<IncidentSummary[]>(
    "/api/v1/incidents",
    fetcher,
    { refreshInterval: 5000 },
  );
  const [sev, setSev] = useState("all");

  const rows = (data ?? []).filter((i) => sev === "all" || i.severity === sev);

  return (
    <div>
      <h1>Incident Queue</h1>
      <p className="muted">
        Inject an incident from the Overview page, then investigate it here.
      </p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <label>
          Severity:{" "}
          <select value={sev} onChange={(e) => setSev(e.target.value)}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <div className="card">Loading incidents…</div>}
      {error && <div className="card"><span className="badge bad">API unreachable</span></div>}
      {data && rows.length === 0 && (
        <div className="card muted">No incidents yet. Inject one from the Overview page.</div>
      )}

      {rows.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Incident</th>
                <th>Severity</th>
                <th>System</th>
                <th>Status</th>
                <th>Investigation</th>
                <th>Confidence</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.incident_id}>
                  <td>
                    <Link href={`/incidents/${i.incident_id}`}>{i.title}</Link>
                    <div className="muted">{i.incident_id}</div>
                  </td>
                  <td>
                    <span className={`badge ${i.severity === "critical" || i.severity === "high" ? "bad" : ""}`}>
                      {i.severity}
                    </span>
                  </td>
                  <td>{i.primary_affected_system}</td>
                  <td>{i.status}</td>
                  <td>{i.has_investigation ? (i.leading_root_cause ?? "done") : "—"}</td>
                  <td>{i.confidence != null ? i.confidence.toFixed(2) : "—"}</td>
                  <td>
                    {i.requires_human_review == null
                      ? "—"
                      : i.requires_human_review
                        ? <span className="badge bad">human</span>
                        : <span className="badge ok">auto</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
