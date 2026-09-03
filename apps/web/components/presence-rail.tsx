"use client";

/**
 * "Who is on this incident" avatars.
 *
 * Simulated peers are visually distinguished (dashed ring) and labelled in the
 * tooltip. A demo that quietly implied three colleagues were watching would be
 * a small lie, and small lies are what make reference implementations
 * untrustworthy.
 */

import { cn, initials } from "@/lib/format";
import type { PresenceEntry } from "@/lib/types";

const ROLE_TINT: Record<string, string> = {
  incident_commander: "bg-immediate-dim text-immediate",
  operations_section: "bg-info-dim text-info",
  logistics_section: "bg-ok-dim text-ok",
  planning_section: "bg-ai-dim text-ai",
  observer: "bg-routine-dim text-muted",
};

export function PresenceRail({ presence }: { presence: PresenceEntry[] }) {
  const live = presence.filter((entry) => !entry.simulated);
  const simulated = presence.filter((entry) => entry.simulated);
  const ordered = [...live, ...simulated].slice(0, 6);

  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-[10px] uppercase tracking-widest text-faint sm:inline">
        On board
      </span>
      <ul className="flex -space-x-1.5" aria-label={`${presence.length} operators viewing`}>
        {ordered.map((entry) => (
          <li key={entry.connection_id}>
            <span
              title={
                entry.simulated
                  ? `${entry.display_name} — simulated peer operator (demo)`
                  : `${entry.display_name} — viewing now`
              }
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-[9.5px] font-bold",
                ROLE_TINT[entry.ics_role] ?? "bg-routine-dim text-muted",
                entry.simulated ? "border-dashed border-faint/70" : "border-line",
              )}
            >
              {initials(entry.display_name)}
            </span>
          </li>
        ))}
      </ul>
      {simulated.length > 0 ? (
        <span
          className="hidden text-[10px] text-faint xl:inline"
          title="Dashed avatars are simulated"
        >
          {live.length} live · {simulated.length} simulated
        </span>
      ) : null}
    </div>
  );
}
