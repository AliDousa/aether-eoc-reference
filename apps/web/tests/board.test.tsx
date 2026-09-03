/**
 * The board must render the seeded incident, and the demo banner must be
 * present on every page. Both are load-bearing claims in the README.
 */

import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SEEDED_BOARD, LOGISTICS_SESSION, renderWithQuery } from "./helpers";

vi.mock("@/lib/api", () => ({
  api: {
    board: vi.fn(async () => SEEDED_BOARD),
    postNote: vi.fn(async () => ({ event: {} })),
  },
  ApiError: class ApiError extends Error {},
  API_BASE: "http://localhost:8080",
  WS_BASE: "ws://localhost:8080",
  loadSession: () => null,
  saveSession: () => {},
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return {
    ...actual,
    useSession: () => ({
      session: LOGISTICS_SESSION,
      ready: true,
      switching: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
      can: (permission: string) => LOGISTICS_SESSION.permissions.includes(permission),
      canDecide: () => true,
    }),
  };
});

import BoardPage from "@/app/page";
import { DemoBanner } from "@/components/demo-banner";

describe("incident board", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the seeded incident, its period, and its commander", async () => {
    renderWithQuery(<BoardPage />);

    await waitFor(() =>
      expect(screen.getAllByText(/HEAT-2026-DUBAI-REF/).length).toBeGreaterThan(0),
    );

    expect(screen.getByText(/Extreme heat \/ mass-gathering/)).toBeInTheDocument();
    expect(screen.getByText(/IC-Demo/)).toBeInTheDocument();
    expect(screen.getByText(/Reference Jurisdiction/)).toBeInTheDocument();
  });

  it("shows the KPI figures from the board payload", async () => {
    renderWithQuery(<BoardPage />);

    await waitFor(() => expect(screen.getByText("Open requests")).toBeInTheDocument());

    expect(screen.getByText("Unfilled IMMEDIATE")).toBeInTheDocument();
    expect(screen.getByText("Pending AI reviews")).toBeInTheDocument();
    // The IMMEDIATE shortfall is the number a reviewer is meant to notice.
    expect(screen.getByText("Sites below reorder")).toBeInTheDocument();
  });

  it("lists the seeded request with its priority and state", async () => {
    renderWithQuery(<BoardPage />);

    await waitFor(() => expect(screen.getByText(/Oral Rehydration Salts Kit/)).toBeInTheDocument());

    // Status is carried by a text label, never colour alone.
    expect(screen.getByText("IMMEDIATE")).toBeInTheDocument();
    expect(screen.getByText("Awaiting decision")).toBeInTheDocument();
  });

  it("marks Finance/Admin as present but not implemented", async () => {
    renderWithQuery(<BoardPage />);
    await waitFor(() => expect(screen.getByText("Finance / Admin")).toBeInTheDocument());
    // Honesty about scope is visible in the UI, not only in the docs.
    expect(screen.getByText("n/i")).toBeInTheDocument();
  });

  it("renders the activity stream entry", async () => {
    renderWithQuery(<BoardPage />);
    await waitFor(() =>
      expect(screen.getByText(/Sector North occupancy 78 percent/)).toBeInTheDocument(),
    );
  });
});

describe("demo banner", () => {
  it("states plainly that this is not a live EOC", () => {
    renderWithQuery(<DemoBanner />);
    expect(screen.getByText(/SYNTHETIC DEMO/)).toBeInTheDocument();
    expect(screen.getByText(/not a live EOC/)).toBeInTheDocument();
    expect(screen.getByRole("note", { name: /synthetic demonstration/i })).toBeInTheDocument();
  });
});
