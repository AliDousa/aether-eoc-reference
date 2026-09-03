/**
 * Shapes returned by the API.
 *
 * Hand-written rather than generated from OpenAPI. The API is small and stable,
 * and a generation step would be one more thing a reviewer has to run before
 * the repo makes sense. `docs/ARCHITECTURE.md` notes where generation would
 * become worth it.
 */

export type Priority = "routine" | "priority" | "immediate";

export type RequestState =
  | "draft"
  | "submitted"
  | "recommended"
  | "approved"
  | "modified"
  | "rejected"
  | "tasked"
  | "fulfilled"
  | "cancelled";

export type IcsRole =
  "incident_commander" | "operations_section" | "logistics_section" | "planning_section";

export type IcsSection = "command" | "operations" | "planning" | "logistics" | "finance_admin";

export type RecommendationStatus = "pending" | "approved" | "modified" | "rejected";

export interface Operator {
  id: string;
  username: string;
  display_name: string;
  ics_role: IcsRole;
  section: IcsSection;
}

export interface DemoOperator {
  username: string;
  display_name: string;
  ics_role: IcsRole;
  section: IcsSection;
  advertised: boolean;
}

export interface Session {
  token: string;
  operator: Operator;
  permissions: string[];
  demo_mode: boolean;
}

export interface Incident {
  id: string;
  name: string;
  type: string;
  severity: string;
  status: string;
  activated_at: string;
  current_period: string;
  period_started_at: string;
  period_ends_at: string;
  commander: { id: string; display_name: string; ics_role: string } | null;
  jurisdiction: string;
  objectives: string[];
}

export interface SectionChip {
  section: IcsSection;
  label: string;
  staffed: boolean;
  operator_count: number;
  implemented: boolean;
}

export interface Kpis {
  open_requests: number;
  unfilled_immediate: number;
  sites_below_reorder: number;
  lines_below_reorder: number;
  pending_ai_reviews: number;
}

export interface ActivityEvent {
  id: string;
  incident_id: string;
  actor_id: string | null;
  actor_name: string;
  kind: string;
  body: string;
  section: IcsSection | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface Citation {
  id: string;
  source: string;
  title: string;
  anchor: string;
  preview: string;
  score: number;
}

export interface AllocationLeg {
  from_site_id: string;
  from_site_name: string;
  quantity: number;
  equity_priority: number;
  available_before: number;
  available_after: number;
}

export interface EquityReview {
  passed: boolean;
  rule_id: string;
  summary: string;
  considered: Array<{
    site_id: string;
    site_name: string;
    equity_priority: number;
    available: number;
    reserve_floor: number;
    max_draw: number;
    drawn: number;
  }>;
  withheld: Array<{
    site_id: string;
    site_name: string;
    equity_priority: number;
    retained: number;
    reason: string;
  }>;
  violations: Array<{ site_id?: string; site_name?: string; reason: string }>;
}

export interface RecommendationPayload {
  sku_code: string;
  destination_site_id: string | null;
  requested_quantity: number;
  allocated_quantity: number;
  shortfall: number;
  fully_filled: boolean;
  legs: AllocationLeg[];
  notes: string[];
  equity_review: EquityReview;
}

export interface Recommendation {
  id: string;
  request_id: string;
  agent: string;
  agent_run_id: string | null;
  payload: RecommendationPayload;
  equity_review: EquityReview;
  citations: string[];
  confidence: number;
  rationale: string;
  status: RecommendationStatus;
  decided_by: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_reason: string;
  decided_payload: Record<string, unknown>;
  created_at: string;
}

export interface ResourceRequest {
  id: string;
  incident_id: string;
  sku: { id: string; code: string; name: string; unit: string; category: string };
  quantity: number;
  priority: Priority;
  requesting_section: IcsSection;
  destination_site: {
    id: string;
    name: string;
    kind: string;
    equity_priority: number;
  } | null;
  justification: string;
  state: RequestState;
  allowed_transitions: RequestState[];
  is_open: boolean;
  created_by: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  recommendation?: Recommendation;
  timeline?: Array<{
    seq: number;
    at: string;
    action: string;
    actor: string;
    correlation_id: string;
    ai_trace_id: string | null;
  }>;
}

export interface InventoryPosition {
  id: string;
  site_id: string;
  site_name: string;
  site_kind: string;
  equity_priority: number;
  sku_id: string;
  sku_code: string;
  sku_name: string;
  category: string;
  unit: string;
  on_hand: number;
  reserved: number;
  available: number;
  reorder_point: number;
  below_reorder: boolean;
  updated_at: string;
}

export interface PresenceEntry {
  connection_id: string;
  operator_id: string;
  display_name: string;
  ics_role: string;
  since: string;
  simulated: boolean;
}

export interface Board {
  incident: Incident;
  status_note: string | null;
  sections: SectionChip[];
  kpis: Kpis;
  requests: ResourceRequest[];
  activity: ActivityEvent[];
  inventory: InventoryPosition[];
  below_reorder: InventoryPosition[];
  presence: PresenceEntry[];
}

export interface AuditEvent {
  seq: number;
  id: string;
  at: string;
  actor_id: string | null;
  actor_label: string;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  correlation_id: string;
  ai_trace_id: string | null;
  prev_hash: string;
  hash: string;
}

export interface AuditPage {
  events: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
  action_counts: Array<{ action: string; count: number }>;
}

export interface ChainVerification {
  ok: boolean;
  checked: number;
  head_hash: string;
  genesis_hash: string;
  broken_at_seq: number | null;
  detail: string;
  problems: string[];
}

export interface AgentResultPayload {
  agent: string;
  intent: string;
  summary: string;
  structured: Record<string, unknown>;
  citations: Citation[];
  confidence: number;
  uncertainty: string[];
  mode: "fixture" | "llm";
  model_id: string;
  requires_human: boolean;
  banner: string;
}

export interface AgentRun {
  id: string;
  incident_id: string;
  agent: string;
  intent: string;
  requested_by: string;
  requested_by_name: string;
  mode: string;
  model_id: string;
  prompt_hash: string;
  retrieved_chunk_ids: string[];
  structured_output: AgentResultPayload | Record<string, unknown>;
  raw_output: string;
  status: string;
  latency_ms: number;
  correlation_id: string;
  created_at: string;
}

export interface AgentSpec {
  name: string;
  label: string;
  intent: string;
  purpose: string;
  will: string[];
  will_not: string[];
  requires_human: boolean;
}

export interface AgentCatalogue {
  agents: AgentSpec[];
  mode: "fixture" | "llm";
  llm_enabled: boolean;
  model_id: string;
  banner: string;
  knowledge_sources: string[];
  recent_runs: AgentRun[];
}

export interface KnowledgeIndex {
  notice: string;
  sources: Array<{
    source: string;
    section_count: number;
    sections: Array<{ id: string; title: string; anchor: string }>;
  }>;
  chunk_count: number;
}

export interface KnowledgeChunk {
  notice: string;
  chunk: { id: string; source: string; anchor: string; title: string; text: string };
}

export interface Health {
  status: string;
  demo_mode: boolean;
  llm_enabled: boolean;
  agent_mode: "fixture" | "llm";
  knowledge_sources: number;
  incident: string | null;
}

export interface Site {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lon: number;
  equity_priority: number;
  notes: string;
}

export interface Sku {
  id: string;
  code: string;
  name: string;
  category: string;
  unit: string;
}

/** WebSocket frame envelope. */
export interface WsFrame {
  type: string;
  at: string;
  payload: Record<string, unknown>;
}
