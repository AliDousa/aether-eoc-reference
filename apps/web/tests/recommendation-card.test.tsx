/**
 * The human-in-the-loop control surface.
 *
 * The important assertion is the negative one: an Operations Section operator
 * must not be offered the decision controls, and must be told why rather than
 * shown a dead greyed-out button.
 */

import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  LOGISTICS_SESSION,
  OPERATIONS_SESSION,
  PENDING_RECOMMENDATION,
  SEEDED_REQUEST,
  renderWithQuery,
} from "./helpers";
import type { Session } from "@/lib/types";

const decide = vi.fn(async () => ({}));

vi.mock("@/lib/api", () => ({
  api: { decide: (...args: unknown[]) => decide(...(args as [])) },
  ApiError: class ApiError extends Error {},
  API_BASE: "http://localhost:8080",
  WS_BASE: "ws://localhost:8080",
  loadSession: () => null,
  saveSession: () => {},
}));

// Mutable so each test can install a different role before rendering.
let activeSession: Session = LOGISTICS_SESSION;

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return {
    ...actual,
    useSession: () => ({
      session: activeSession,
      ready: true,
      switching: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
      can: (permission: string) => activeSession.permissions.includes(permission),
      canDecide: (agent: string) =>
        activeSession.permissions.includes("recommendation:decide:any") ||
        (agent === "resource_recommender" &&
          activeSession.permissions.includes("recommendation:decide:logistics")),
    }),
  };
});

import { RecommendationCard } from "@/components/recommendation-card";

describe("recommendation card", () => {
  it("disables the decision buttons for the Operations Section", async () => {
    activeSession = OPERATIONS_SESSION;

    renderWithQuery(
      <RecommendationCard request={SEEDED_REQUEST} recommendation={PENDING_RECOMMENDATION} />,
    );

    const approve = await screen.findByRole("button", { name: /approve as recommended/i });
    const reject = screen.getByRole("button", { name: /reject/i });

    expect(approve).toBeDisabled();
    expect(reject).toBeDisabled();

    // And the reason is written out, not left for the operator to infer.
    expect(screen.getByText(/does not hold\s+authority to commit resources/i)).toBeInTheDocument();
    expect(screen.getByText(/The server enforces this/i)).toBeInTheDocument();
  });

  it("enables approval for the Logistics Section", async () => {
    activeSession = LOGISTICS_SESSION;

    renderWithQuery(
      <RecommendationCard request={SEEDED_REQUEST} recommendation={PENDING_RECOMMENDATION} />,
    );

    const approve = await screen.findByRole("button", { name: /approve as recommended/i });
    expect(approve).toBeEnabled();

    // Rejection still requires a written reason, so it starts disabled.
    expect(screen.getByRole("button", { name: /reject/i })).toBeDisabled();
  });

  it("shows the verify banner, the shortfall, and the equity review", async () => {
    activeSession = LOGISTICS_SESSION;

    renderWithQuery(
      <RecommendationCard request={SEEDED_REQUEST} recommendation={PENDING_RECOMMENDATION} />,
    );

    await waitFor(() => expect(screen.getByText(/AI-suggested/)).toBeInTheDocument());
    expect(screen.getByText(/Nothing moves until a human approves it/i)).toBeInTheDocument();

    // The shortfall is stated, never rounded away.
    expect(screen.getByText(/Short 90 kit/)).toBeInTheDocument();

    // The equity floor result and what it protected are both visible.
    expect(screen.getByText("Equity floor OK")).toBeInTheDocument();
    expect(screen.getByText(/retains 20 unit\(s\) under the equity floor/i)).toBeInTheDocument();

    // Both proposed source sites are listed.
    expect(screen.getByText("Field Staging")).toBeInTheDocument();
    expect(screen.getByText("Central Cache")).toBeInTheDocument();
  });

  it("does not offer decision controls once a decision has been made", async () => {
    activeSession = LOGISTICS_SESSION;

    renderWithQuery(
      <RecommendationCard
        request={{ ...SEEDED_REQUEST, state: "modified" }}
        recommendation={{
          ...PENDING_RECOMMENDATION,
          status: "modified",
          decided_by: "opr_log",
          decided_by_name: "LOGISTICS-1",
          decided_at: new Date().toISOString(),
          decision_reason: "Reduced the first leg; holding reserve for OP-3.",
        }}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Human decision/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /approve as recommended/i })).toBeNull();
    expect(screen.getByText(/Reduced the first leg/)).toBeInTheDocument();
    expect(screen.getByText("LOGISTICS-1")).toBeInTheDocument();
  });
});
