// Types mirroring the backend response schemas.

export interface HealthResponse {
  status: string;
  version: string;
}

export interface SystemStatusResponse {
  status: string;
  version: string;
  environment: string;
  database_backend: string;
  database_reachable: boolean;
  llm_provider: string;
  seed: number;
  table_counts: Record<string, number>;
}

export interface LineageNode {
  id: string;
  type: string;
  label: string;
  metadata: Record<string, unknown>;
}

export interface LineageEdge {
  source: string;
  target: string;
  type: string;
}

export interface LineageQueryResult {
  root: string;
  direction: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
  paths: string[][];
  affected_assets: string[];
}
