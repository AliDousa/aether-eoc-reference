"use client";

/**
 * ICS role switcher.
 *
 * Performs a real login as another seeded operator, so authority genuinely
 * changes: as Operations, the approve controls are not merely hidden — the
 * server refuses the call. See lib/session.tsx.
 */

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ShieldCheck, UserCog } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/format";
import { ROLE_LABEL, SWITCHABLE_ROLES, useSession } from "@/lib/session";

export function RoleSwitcher() {
  const { session, login, logout, switching, ready } = useSession();
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const choose = async (username: string) => {
    setOpen(false);
    try {
      await login(username);
      // Permissions changed, so anything gated on them must be refetched, and
      // presence changes because the socket reconnects with the new token.
      await queryClient.invalidateQueries();
    } catch {
      /* the error is surfaced by the session context */
    }
  };

  if (!ready) {
    return <div className="h-7 w-32 animate-pulse rounded bg-panel-2" aria-hidden="true" />;
  }

  if (!session) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="hidden text-[11px] text-muted sm:inline">Read-only</span>
        {SWITCHABLE_ROLES.map((role) => (
          <button
            key={role.username}
            type="button"
            className="btn px-2 py-1 text-[11px]"
            disabled={switching}
            onClick={() => void choose(role.username)}
            title={`Sign in as ${role.label} (demo password)`}
          >
            {role.short}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="btn gap-2 py-1"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        disabled={switching}
      >
        <UserCog size={13} aria-hidden="true" />
        <span className="hidden text-[12px] sm:inline">{session.operator.display_name}</span>
        <span className="text-[10px] uppercase tracking-wider text-muted">
          {ROLE_LABEL[session.operator.ics_role].replace(" Section", "")}
        </span>
        <ChevronDown size={12} aria-hidden="true" />
      </button>

      {open ? (
        <>
          {/* Click-away layer */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div
            role="menu"
            className="absolute right-0 z-20 mt-1 w-64 rounded border border-line bg-panel shadow-xl"
          >
            <div className="border-b border-line px-3 py-2">
              <p className="text-[10px] uppercase tracking-widest text-faint">Act as</p>
              <p className="text-[11px] text-muted">
                Switching changes real authority, not just the view.
              </p>
            </div>
            {SWITCHABLE_ROLES.map((role) => {
              const active = session.operator.username === role.username;
              return (
                <button
                  key={role.username}
                  type="button"
                  role="menuitem"
                  onClick={() => void choose(role.username)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] transition-colors",
                    active ? "bg-raised text-ink" : "text-ink-2 hover:bg-panel-2",
                  )}
                >
                  <span>
                    <span className="font-medium">{role.label}</span>
                    <span className="block text-[10px] text-faint">{role.username}</span>
                  </span>
                  {active ? <ShieldCheck size={13} className="text-ok" aria-hidden="true" /> : null}
                </button>
              );
            })}
            <div className="border-t border-line px-3 py-2">
              <p className="mb-1.5 text-[10px] text-faint">
                {session.permissions.includes("recommendation:decide:any")
                  ? "May approve any recommendation."
                  : session.permissions.includes("recommendation:decide:logistics")
                    ? "May approve logistics recommendations."
                    : "May not approve resource movements."}
              </p>
              <button
                type="button"
                className="btn-ghost btn w-full py-1 text-[11px]"
                onClick={logout}
              >
                Sign out (read-only)
              </button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
