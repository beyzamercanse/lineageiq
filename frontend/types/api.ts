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

export interface IncidentSummary {
  incident_id: string;
  title: string;
  detected_at: string;
  severity: string;
  status: string;
  primary_affected_system: string | null;
  has_investigation: boolean;
  confidence: number | null;
  requires_human_review: boolean | null;
  leading_root_cause: string | null;
}

export interface EvidenceOut {
  evidence_id: string;
  evidence_type: string;
  source: string;
  summary: string;
  collected_at: string;
  reliability_score: number;
  structured_payload: Record<string, unknown> | null;
}

export interface RootCauseCandidate {
  rank: number;
  root_cause_code: string;
  title: string;
  explanation: string;
  confidence: number;
  supporting_evidence_ids: string[];
  affected_systems: string[];
}

export interface RecommendedCheck {
  priority: number;
  action: string;
  reason: string;
  expected_signal: string;
  requires_human: boolean;
}

export interface RemediationRecommendation {
  action: string;
  target_system: string;
  risk: string;
  requires_approval: boolean;
}

export interface InvestigationReport {
  incident_id: string;
  summary: string;
  observations: string[];
  root_cause_candidates: RootCauseCandidate[];
  impacted_systems: string[];
  impacted_reports: string[];
  confidence: number;
  evidence_ids: string[];
  recommended_checks: RecommendedCheck[];
  remediation_recommendations: RemediationRecommendation[];
  requires_human_review: boolean;
  human_review_reason: string | null;
  unsupported_claims: string[];
}

export interface AgentRunOut {
  agent_run_id: string;
  incident_id: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  model_name: string;
  tool_call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost: number;
  output: (InvestigationReport & { validation?: Record<string, unknown> }) | null;
}

export interface GroundTruthOut {
  root_cause_code: string;
  root_cause_description: string;
  affected_tables: string[];
  affected_reports: string[];
  should_escalate: boolean;
}

export interface IncidentDetail {
  incident: IncidentSummary;
  evidence: EvidenceOut[];
  agent_runs: AgentRunOut[];
  ground_truth: GroundTruthOut | null;
}
