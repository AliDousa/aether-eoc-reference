/**
 * Test helpers for the web suite.
 *
 * The API is mocked at the module boundary (`@/lib/api`) rather than over the
 * network, so these tests run in CI with no API key, no database, and no
 * server — which is the requirement for the CI job.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import type { Board, Recommendation, ResourceRequest, Session } from "@/lib/types";

export function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false, staleTime: Infinity },
    },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

export const OPERATIONS_SESSION: Session = {
  token: "test-token",
  operator: {
    id: "opr_ops",
    username: "ops.demo",
    display_name: "OPERATIONS-1",
    ics_role: "operations_section",
    section: "operations",
  },
  // Note what is absent: no recommendation:decide:* permission at all.
  permissions: ["activity:post", "agent:run", "request:create", "request:submit"],
  demo_mode: true,
};

export const LOGISTICS_SESSION: Session = {
  token: "test-token",
  operator: {
    id: "opr_log",
    username: "logistics.demo",
    display_name: "LOGISTICS-1",
    ics_role: "logistics_section",
    section: "logistics",
  },
  permissions: [
    "activity:post",
    "agent:run",
    "recommendation:decide:logistics",
    "request:create",
    "request:submit",
  ],
  demo_mode: true,
};

export const SEEDED_REQUEST: ResourceRequest = {
  id: "req_test0001",
  incident_id: "inc_heat_2026",
  sku: {
    id: "sku_ors",
    code: "ORS-KIT",
    name: "Oral Rehydration Salts Kit",
    unit: "kit",
    category: "medical",
  },
  quantity: 400,
  priority: "immediate",
  requesting_section: "operations",
  destination_site: {
    id: "site_north",
    name: "Sector North Cooling Center",
    kind: "cooling_center",
    equity_priority: 5,
  },
  justification: "Sector North holds 25 kits against a reorder point of 80.",
  state: "recommended",
  allowed_transitions: ["approved", "cancelled", "modified", "rejected"],
  is_open: true,
  created_by: "opr_ops",
  created_by_name: "OPERATIONS-1",
  created_at: new Date(Date.now() - 3_600_000).toISOString(),
  updated_at: new Date().toISOString(),
};

export const PENDING_RECOMMENDATION: Recommendation = {
  id: "rec_test0001",
  request_id: SEEDED_REQUEST.id,
  agent: "resource_recommender",
  agent_run_id: "run_test0001",
  payload: {
    sku_code: "ORS-KIT",
    destination_site_id: "site_north",
    requested_quantity: 400,
    allocated_quantity: 310,
    shortfall: 90,
    fully_filled: false,
    legs: [
      {
        from_site_id: "site_staging",
        from_site_name: "Field Staging",
        quantity: 90,
        equity_priority: 1,
        available_before: 90,
        available_after: 0,
      },
      {
        from_site_id: "site_cache",
        from_site_name: "Central Cache",
        quantity: 180,
        equity_priority: 2,
        available_before: 180,
        available_after: 0,
      },
    ],
    notes: ["Shortfall of 90 unit(s)."],
    equity_review: {
      passed: true,
      rule_id: "resource-allocation-equity-rules.md#3-the-equity-floor-hard-constraint",
      summary: "Equity floor satisfied, but it caps the fill.",
      considered: [],
      withheld: [
        {
          site_id: "site_south",
          site_name: "Sector South Cooling Center",
          equity_priority: 4,
          retained: 20,
          reason: "Equity priority 4 site retains 20 unit(s) under the equity floor.",
        },
      ],
      violations: [],
    },
  },
  equity_review: {
    passed: true,
    rule_id: "resource-allocation-equity-rules.md#3-the-equity-floor-hard-constraint",
    summary: "Equity floor satisfied.",
    considered: [],
    withheld: [],
    violations: [],
  },
  citations: ["resource-allocation-equity-rules.md#3-the-equity-floor-hard-constraint"],
  confidence: 0.62,
  rationale: "Allocate 310 of 400 Oral Rehydration Salts Kit to Sector North Cooling Center.",
  status: "pending",
  decided_by: null,
  decided_by_name: null,
  decided_at: null,
  decision_reason: "",
  decided_payload: {},
  created_at: new Date().toISOString(),
};

export const SEEDED_BOARD: Board = {
  incident: {
    id: "inc_heat_2026",
    name: "HEAT-2026-DUBAI-REF",
    type: "Extreme heat / mass-gathering public-health surge",
    severity: "major",
    status: "active",
    activated_at: new Date(Date.now() - 6 * 3_600_000).toISOString(),
    current_period: "OP-2",
    period_started_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
    period_ends_at: new Date(Date.now() + 10 * 3_600_000).toISOString(),
    commander: { id: "opr_ic", display_name: "IC-Demo", ics_role: "incident_commander" },
    jurisdiction: "Reference Jurisdiction (synthetic)",
    objectives: ["Prevent heat-related mortality across both sectors."],
  },
  status_note: null,
  sections: [
    { section: "command", label: "Command", staffed: true, operator_count: 1, implemented: true },
    {
      section: "operations",
      label: "Operations",
      staffed: true,
      operator_count: 3,
      implemented: true,
    },
    { section: "planning", label: "Planning", staffed: true, operator_count: 1, implemented: true },
    {
      section: "logistics",
      label: "Logistics",
      staffed: true,
      operator_count: 1,
      implemented: true,
    },
    {
      section: "finance_admin",
      label: "Finance / Admin",
      staffed: false,
      operator_count: 0,
      implemented: false,
    },
  ],
  kpis: {
    open_requests: 4,
    unfilled_immediate: 1,
    sites_below_reorder: 3,
    lines_below_reorder: 7,
    pending_ai_reviews: 0,
  },
  requests: [SEEDED_REQUEST],
  activity: [
    {
      id: "act_0001",
      incident_id: "inc_heat_2026",
      actor_id: "opr_north",
      actor_name: "Operator North",
      kind: "log_note",
      body: "Sector North occupancy 78 percent and climbing.",
      section: "operations",
      meta: {},
      created_at: new Date(Date.now() - 900_000).toISOString(),
    },
  ],
  inventory: [
    {
      id: "inv_000",
      site_id: "site_north",
      site_name: "Sector North Cooling Center",
      site_kind: "cooling_center",
      equity_priority: 5,
      sku_id: "sku_ors",
      sku_code: "ORS-KIT",
      sku_name: "Oral Rehydration Salts Kit",
      category: "medical",
      unit: "kit",
      on_hand: 25,
      reserved: 0,
      available: 25,
      reorder_point: 80,
      below_reorder: true,
      updated_at: new Date().toISOString(),
    },
  ],
  below_reorder: [],
  presence: [
    {
      connection_id: "sim-log-2",
      operator_id: "opr_sim_log2",
      display_name: "LOGISTICS-2",
      ics_role: "logistics_section",
      since: new Date().toISOString(),
      simulated: true,
    },
  ],
};
