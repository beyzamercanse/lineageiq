"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { LineageNode, LineageQueryResult } from "@/types/api";

function NodeList({ title, result }: { title: string; result?: LineageQueryResult }) {
  return (
    <div className="card" style={{ flex: 1 }}>
      <h3>{title}</h3>
      {!result && <p className="muted">Select a node.</p>}
      {result && (
        <ul style={{ paddingLeft: "1rem" }}>
          {result.nodes
            .filter((n) => n.id !== result.root)
            .map((n) => (
              <li key={n.id}>
                {n.label} <span className="muted">({n.type})</span>
              </li>
            ))}
          {result.nodes.length <= 1 && <li className="muted">none</li>}
        </ul>
      )}
    </div>
  );
}

export default function LineagePage() {
  const { data: nodes } = useSWR<LineageNode[]>("/api/v1/lineage/nodes", fetcher);
  const [focus, setFocus] = useState<string>("fx_rates");

  const { data: impact } = useSWR<LineageQueryResult>(
    focus ? `/api/v1/lineage/impact?node_id=${focus}` : null,
    fetcher,
  );
  const { data: upstream } = useSWR<LineageQueryResult>(
    focus ? `/api/v1/lineage/upstream?node_id=${focus}` : null,
    fetcher,
  );

  return (
    <div>
      <h1>Lineage Explorer</h1>
      <p className="muted">
        Trace dependencies through AtlasCommerce. Pick a node to see what feeds
        it (upstream) and what it impacts (downstream).
      </p>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <label>
          Focus node:{" "}
          <select value={focus} onChange={(e) => setFocus(e.target.value)}>
            {(nodes ?? []).map((n) => (
              <option key={n.id} value={n.id}>
                {n.label} ({n.type})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem" }}>
        <NodeList title="⬆ Upstream (feeds it)" result={upstream} />
        <NodeList title="⬇ Downstream (it feeds)" result={impact} />
      </div>

      {impact && impact.affected_assets.length > 0 && (
        <div className="card" style={{ marginBottom: "1rem" }}>
          <h3>Impacted business assets</h3>
          {impact.affected_assets.map((a) => (
            <span key={a} className="badge bad" style={{ marginRight: "0.4rem" }}>
              {a}
            </span>
          ))}
        </div>
      )}

      {impact && impact.paths.length > 0 && (
        <div className="card">
          <h3>Dependency paths</h3>
          {impact.paths.slice(0, 8).map((p, i) => (
            <div key={i} className="muted" style={{ fontFamily: "monospace" }}>
              {p.join(" → ")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
