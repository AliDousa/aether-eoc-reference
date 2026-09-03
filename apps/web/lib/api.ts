/**
 * Typed API client.
 *
 * One place that knows how to talk to the API: base URL, bearer token,
 * correlation id, and error shape. Everything else calls these functions.
 */

import type {
  AgentCatalogue,
  AgentResultPayload,
  AgentRun,
  AuditPage,
  Board,
  ChainVerification,
  ChainVerification as Chain,
  DemoOperator,
  Health,
  InventoryPosition,
  KnowledgeChunk,
  KnowledgeIndex,
  Priority,
  Recommendation,
  RequestState,
  ResourceRequest,
  Session,
  Site,
  Sku,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";
export const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE ?? "ws://localhost:8080";

/** Error carrying the API's structured body so the UI can explain *why*. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;

  constructor(status: number, code: string, message: string, detail: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const TOKEN_KEY = "aether-eoc.session";

/**
 * The bearer token lives in localStorage.
 *
 * This is a demo-only choice: it is XSS-exposed, and a real deployment would
 * use a same-origin httpOnly cookie. Stated in docs/THREAT_MODEL.md rather
 * than left for a reviewer to find.
 */
export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session | null): void {
  if (typeof window === "undefined") return;
  try {
    if (session) window.localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Private browsing or blocked storage: the app still works, login just
       does not persist across reloads. */
  }
}

function newCorrelationId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 8)
      : Math.random().toString(16).slice(2, 10);
  return `cor_${random}`;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  /** Ties every write caused by one user action together in the audit log. */
  correlationId?: string;
  searchParams?: Record<string, string | number | undefined>;
}

async function call<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, correlationId, searchParams } = options;

  const url = new URL(path, API_BASE);
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      // URL encodes values for us — important for chunk ids, which contain '#'.
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {
    "X-Correlation-Id": correlationId ?? newCorrelationId(),
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const session = loadSession();
  if (session?.token) headers["Authorization"] = `Bearer ${session.token}`;

  const response = await fetch(url.toString(), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok) {
    let code = "http_error";
    let message = `${response.status} ${response.statusText}`;
    let detail: Record<string, unknown> = {};
    try {
      const parsed = (await response.json()) as Record<string, unknown>;
      // FastAPI validation errors nest under `detail`; ours are flat.
      const nested = parsed.detail as Record<string, unknown> | undefined;
      code = (parsed.code as string) ?? (nested?.code as string) ?? code;
      message = (parsed.message as string) ?? (nested?.message as string) ?? message;
      detail = (parsed.detail as Record<string, unknown>) ?? {};
    } catch {
      /* non-JSON error body; keep the status line */
    }
    throw new ApiError(response.status, code, message, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => call<Health>("/api/health"),

  demoOperators: () => call<DemoOperator[]>("/api/auth/demo-operators"),

  login: (username: string, password: string) =>
    call<Session>("/api/auth/login", { method: "POST", body: { username, password } }),

  board: () => call<Board>("/api/incidents/current"),

  postNote: (incidentId: string, body: string, correlationId?: string) =>
    call<{ event: unknown }>(`/api/incidents/${incidentId}/activity`, {
      method: "POST",
      body: { body },
      correlationId,
    }),

  requests: () => call<{ requests: ResourceRequest[] }>("/api/requests"),

  request: (id: string) => call<ResourceRequest>(`/api/requests/${id}`),

  createRequest: (
    payload: {
      sku_id: string;
      quantity: number;
      priority: Priority;
      requesting_section: string;
      destination_site_id: string;
      justification: string;
    },
    correlationId?: string,
  ) =>
    call<{ request: ResourceRequest }>("/api/requests", {
      method: "POST",
      body: payload,
      correlationId,
    }),

  transitionRequest: (id: string, target: RequestState, note = "", correlationId?: string) =>
    call<{ request: ResourceRequest }>(`/api/requests/${id}/transition`, {
      method: "POST",
      body: { target, note },
      correlationId,
    }),

  recommend: (id: string, correlationId?: string) =>
    call<{ request: ResourceRequest; agent_run: AgentRun; result: AgentResultPayload }>(
      `/api/requests/${id}/recommend`,
      { method: "POST", correlationId },
    ),

  decide: (
    recommendationId: string,
    payload: {
      decision: "approve" | "modify" | "reject";
      reason?: string;
      modified_legs?: Array<{
        from_site_id: string;
        from_site_name: string;
        quantity: number;
        equity_priority: number;
      }>;
      override_equity?: boolean;
    },
    correlationId?: string,
  ) =>
    call<{
      request: ResourceRequest;
      moved_total: number;
      audit: { decision_event_id: string; inventory_event_ids: string[] };
      inventory: InventoryPosition[];
    }>(`/api/recommendations/${recommendationId}/decide`, {
      method: "POST",
      body: payload,
      correlationId,
    }),

  inventory: () =>
    call<{ positions: InventoryPosition[]; below_reorder: InventoryPosition[] }>("/api/inventory"),

  sites: () => call<{ sites: Site[] }>("/api/sites"),

  skus: () => call<{ skus: Sku[] }>("/api/skus"),

  audit: (params: {
    action_prefix?: string;
    entity_id?: string;
    correlation_id?: string;
    limit?: number;
    offset?: number;
  }) => call<AuditPage>("/api/audit", { searchParams: params }),

  verifyChain: () => call<ChainVerification>("/api/audit/verify"),

  agents: () => call<AgentCatalogue>("/api/agents"),

  agentRuns: (limit = 25) =>
    call<{ runs: AgentRun[] }>("/api/agents/runs", { searchParams: { limit } }),

  runAgent: (
    payload: { intent: string; question?: string; request_id?: string },
    correlationId?: string,
  ) =>
    call<{ run: AgentRun; result: AgentResultPayload; recommendation?: Recommendation }>(
      "/api/agents/run",
      { method: "POST", body: payload, correlationId },
    ),

  knowledge: () => call<KnowledgeIndex>("/api/knowledge"),

  knowledgeSource: (source: string) =>
    call<{ notice: string; source: string; text: string; sections: unknown[] }>(
      `/api/knowledge/${source}`,
    ),

  // The id contains '#', so it must go through searchParams (which encodes it)
  // rather than string interpolation into the path.
  knowledgeChunk: (id: string) =>
    call<KnowledgeChunk>("/api/knowledge/chunk", { searchParams: { id } }),
};

export type { Chain };
