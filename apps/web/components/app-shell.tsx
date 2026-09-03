"use client";

/**
 * Application chrome: left nav, top bar, presence rail, role switcher.
 *
 * The top bar carries the four facts an operator needs without scrolling:
 * which incident, which operational period and how long is left, who else is
 * on the board, and whose authority they are currently acting with.
 */

import { useQuery } from "@tanstack/react-query";
import { Activity, BookOpen, Bot, ClipboardList, Radio, ScrollText, WifiOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { DemoBanner } from "@/components/demo-banner";
import { PresenceRail } from "@/components/presence-rail";
import { RoleSwitcher } from "@/components/role-switcher";
import { api } from "@/lib/api";
import { cn, untilPeriodEnd } from "@/lib/format";
import { useIncidentSocket } from "@/lib/ws";

const NAV: Array<{ href: string; label: string; Icon: LucideIcon }> = [
  { href: "/", label: "Incident", Icon: Activity },
  { href: "/requests", label: "Requests", Icon: ClipboardList },
  { href: "/agents", label: "Agents", Icon: Bot },
  { href: "/audit", label: "Audit", Icon: ScrollText },
  { href: "/knowledge", label: "Knowledge", Icon: BookOpen },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  const { data: board } = useQuery({
    queryKey: ["board"],
    queryFn: api.board,
  });

  const incidentId = board?.incident.id;
  const live = useIncidentSocket(incidentId);
  // Presence from the socket once connected; the board snapshot covers the
  // moment before the socket opens so the rail is never empty.
  const presence = live.presence.length > 0 ? live.presence : (board?.presence ?? []);

  return (
    <div className="min-h-screen bg-base">
      <DemoBanner />

      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <div className="flex min-h-[calc(100vh-24px)] flex-col lg:flex-row">
        {/* Left nav. Becomes a horizontal strip on small screens. */}
        <nav
          aria-label="Sections"
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-panel px-2 py-2 lg:w-48 lg:flex-col lg:overflow-visible lg:border-b-0 lg:border-r lg:px-2 lg:py-3"
        >
          <div className="mb-2 hidden px-2 lg:block">
            <div className="text-[13px] font-semibold tracking-tight text-ink">Aether EOC</div>
            <div className="text-[10px] uppercase tracking-widest text-faint">Reference slice</div>
          </div>

          {NAV.map(({ href, label, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 whitespace-nowrap rounded px-2.5 py-1.5 text-[13px] transition-colors",
                  active
                    ? "bg-raised font-semibold text-ink"
                    : "text-ink-2 hover:bg-panel-2 hover:text-ink",
                )}
              >
                <Icon size={14} aria-hidden="true" />
                {label}
              </Link>
            );
          })}

          <div className="mt-auto hidden px-2 pt-4 lg:block">
            <ConnectionPill state={live.state} />
          </div>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Top bar */}
          <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-panel px-3 py-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-[15px] font-semibold tracking-tight text-ink">
                  {board?.incident.name ?? "Loading incident…"}
                </h1>
                {board ? (
                  <span className="chip border-immediate/40 bg-immediate-dim text-immediate">
                    {board.incident.severity.toUpperCase()}
                  </span>
                ) : null}
              </div>
              <p className="truncate text-[11px] text-muted">
                {board?.incident.type ?? "—"}
                {board ? ` · ${board.incident.jurisdiction}` : ""}
              </p>
            </div>

            {board ? (
              <div className="flex items-center gap-1.5 rounded border border-line bg-base px-2 py-1">
                <span className="text-[10px] uppercase tracking-widest text-faint">Period</span>
                <span className="text-[13px] font-semibold text-ink">
                  {board.incident.current_period}
                </span>
                <span className="mono text-info">
                  {untilPeriodEnd(board.incident.period_ends_at)}
                </span>
              </div>
            ) : null}

            <div className="ml-auto flex items-center gap-3">
              <PresenceRail presence={presence} />
              <div className="lg:hidden">
                <ConnectionPill state={live.state} compact />
              </div>
              <RoleSwitcher />
            </div>
          </header>

          <main id="main" className="min-w-0 flex-1 p-3">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

function ConnectionPill({
  state,
  compact = false,
}: {
  state: "connecting" | "open" | "closed";
  compact?: boolean;
}) {
  // Live/degraded is stated in words, not only by dot colour: whether the
  // board is receiving updates is exactly the kind of thing an operator must
  // not have to infer.
  if (state === "open") {
    return (
      <span className="chip border-ok/35 bg-ok-dim text-ok" title="Receiving live board updates">
        <Radio size={11} aria-hidden="true" />
        {compact ? "Live" : "Live updates on"}
      </span>
    );
  }
  if (state === "connecting") {
    return (
      <span className="chip border-line bg-routine-dim text-muted">
        <Radio size={11} aria-hidden="true" />
        Connecting…
      </span>
    );
  }
  return (
    <span
      className="chip border-priority/40 bg-priority-dim text-priority"
      title="WebSocket is down. The board is still refreshing on a timer."
    >
      <WifiOff size={11} aria-hidden="true" />
      {compact ? "Polling" : "Offline — polling"}
    </span>
  );
}
