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
