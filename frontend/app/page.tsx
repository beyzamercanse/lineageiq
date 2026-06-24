"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { SystemStatusResponse } from "@/types/api";

export default function OverviewPage() {
  const { data, error, isLoading } = useSWR<SystemStatusResponse>(
    "/api/v1/system/status",
    fetcher,
    { refreshInterval: 10000 },
  );

  return (
    <div>
      <h1>Operations Overview</h1>
      <p className="muted">
        AtlasCommerce — synthetic multi-system enterprise. All data is fictional.
      </p>

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
                <span
                  className={`badge ${data.database_reachable ? "ok" : "bad"}`}
                >
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
              Seed {data.seed}. Run <code>make seed</code> to generate the clean
              dataset.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
