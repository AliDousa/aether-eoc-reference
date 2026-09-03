"use client";

/**
 * Session and ICS role context.
 *
 * The role switcher in the top bar performs a real login as a different seeded
 * operator rather than filtering the UI client-side. That matters: switching to
 * Operations must actually remove the authority to approve a resource
 * movement, not merely grey out a button. A demo where the guardrail is only
 * cosmetic would be arguing the opposite of what this repo is arguing.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

import { api } from "./api";
import {
  getHydratedServerSnapshot,
  getHydratedSnapshot,
  getServerSnapshot,
  getSnapshot,
  setStoredSession,
  subscribe,
  subscribeHydrated,
} from "./session-store";
import type { IcsRole, Session } from "./types";

/** Demo passwords are public; see SECURITY.md. */
const DEMO_PASSWORD = "demo";

/** The three roles the demo script walks through, in board order. */
export const SWITCHABLE_ROLES: Array<{
  username: string;
  label: string;
  short: string;
  role: IcsRole;
}> = [
  { username: "ic.demo", label: "Incident Commander", short: "IC", role: "incident_commander" },
  { username: "ops.demo", label: "Operations", short: "OPS", role: "operations_section" },
  { username: "logistics.demo", label: "Logistics", short: "LOG", role: "logistics_section" },
];

export const Permission = {
  postActivity: "activity:post",
  createRequest: "request:create",
  submitRequest: "request:submit",
  runAgent: "agent:run",
  decideLogistics: "recommendation:decide:logistics",
  decideAny: "recommendation:decide:any",
} as const;

interface SessionContextValue {
  session: Session | null;
  ready: boolean;
  switching: boolean;
  error: string | null;
  login: (username: string, password?: string) => Promise<void>;
  logout: () => void;
  can: (permission: string) => boolean;
  /** True if this operator may decide a recommendation from `agent`. */
  canDecide: (agent: string) => boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  // Read straight from the external store. No effect, no cascading render, and
  // no hydration mismatch: the server snapshot is "signed out" by definition.
  const session = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const ready = useSyncExternalStore(
    subscribeHydrated,
    getHydratedSnapshot,
    getHydratedServerSnapshot,
  );
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (username: string, password: string = DEMO_PASSWORD) => {
    setSwitching(true);
    setError(null);
    try {
      const next = await api.login(username, password);
      setStoredSession(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
      throw cause;
    } finally {
      setSwitching(false);
    }
  }, []);

  const logout = useCallback(() => {
    setStoredSession(null);
  }, []);

  const can = useCallback(
    (permission: string) => Boolean(session?.permissions.includes(permission)),
    [session],
  );

  const canDecide = useCallback(
    (agent: string) => {
      if (!session) return false;
      if (session.permissions.includes(Permission.decideAny)) return true;
      // Mirrors LOGISTICS_SCOPE_AGENTS on the server. The server is still the
      // authority; this only decides whether to render the control.
      return (
        agent === "resource_recommender" && session.permissions.includes(Permission.decideLogistics)
      );
    },
    [session],
  );

  const value = useMemo<SessionContextValue>(
    () => ({ session, ready, switching, error, login, logout, can, canDecide }),
    [session, ready, switching, error, login, logout, can, canDecide],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside <SessionProvider>.");
  return context;
}

export const ROLE_LABEL: Record<IcsRole, string> = {
  incident_commander: "Incident Commander",
  operations_section: "Operations Section",
  logistics_section: "Logistics Section",
  planning_section: "Planning Section",
};
