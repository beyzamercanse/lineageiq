"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { apiPost, fetcher } from "@/lib/api";
import type { IncidentSummary, SystemStatusResponse } from "@/types/api";

interface ManifestSummary {
  manifest_id: string;
  incident_type: string;
  title: string;
  severity: string;
}

export default function OverviewPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<SystemStatusResponse>(
    "/api/v1/system/status",
    fetcher,
    { refreshInterval: 10000 },
  );
  const { data: manifests } = useSWR<ManifestSummary[]>("/api/v1/demo/manifests", fetcher);
  const [selected, setSelected] = useState("stale_fx_rate-01");
  const [busy, setBusy] = useState<string | null>(null);

  async function seed() {
    setBusy("Seeding clean dataset…");
    try {
      await apiPost("/api/v1/demo/seed");
    } finally {
      setBusy(null);
    }
  }

  async function inject() {
    setBusy("Injecting incident + detecting…");
    try {
      const incident = await apiPost<IncidentSummary>(`/api/v1/demo/inject/${selected}`);
      router.push(`/incidents/${incident.incident_id}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h1>Operations Overview</h1>
      <p className="muted">
        AtlasCommerce — synthetic multi-system enterprise. All data is fictional.
      </p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>Demo controls</h3>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={seed} disabled={busy != null}>
            1. Seed clean data
          </button>
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {(manifests ?? []).map((m) => (
              <option key={m.manifest_id} value={m.manifest_id}>
                {m.manifest_id} — {m.title}
              </option>
            ))}
          </select>
          <button onClick={inject} disabled={busy != null}>
            2. Inject + detect
          </button>
        </div>
        {busy && <p className="muted">{busy}</p>}
      </div>

      {isLoading && <div className="card">Loading system status…</div>}
      {error && (
        <div className="card">
          <span className="badge bad">API unreachable</span>
          <p className="muted">
            Could not reach the backend. Start it with <code>make dev</code>.
          </p>
        </div>
      )}

      {data && (
        <>
          <div className="grid" style={{ marginBottom: "1rem" }}>
            <div className="card">
              <div className="muted">System status</div>
              <div className="metric">
                <span className={`badge ${data.database_reachable ? "ok" : "bad"}`}>
                  {data.status}
                </span>
              </div>
            </div>
            <div className="card">
              <div className="muted">Environment</div>
              <div className="metric">{data.environment}</div>
            </div>
            <div className="card">
              <div className="muted">Database</div>
              <div className="metric">{data.database_backend}</div>
            </div>
            <div className="card">
              <div className="muted">LLM provider</div>
              <div className="metric">{data.llm_provider}</div>
            </div>
          </div>

          <div className="card">
            <h3>Data volumes</h3>
            <table>
              <thead>
                <tr>
                  <th>Table</th>
                  <th>Rows</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.table_counts).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td>{v.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              Seed {data.seed}.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
