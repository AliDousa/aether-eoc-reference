"use client";

/**
 * The four numbers on the board header.
 *
 * Chosen because each one has an owner and an action behind it. A KPI nobody
 * can act on is decoration, and a duty floor has no room for decoration.
 */

import { AlertTriangle, Bot, ClipboardList, PackageMinus } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/format";
import type { Kpis } from "@/lib/types";

interface Card {
  label: string;
  value: number;
  hint: string;
  href: string;
  Icon: LucideIcon;
  /** Emphasis when non-zero: these are the numbers that mean "act now". */
  urgent?: boolean;
}

export function KpiCards({ kpis }: { kpis: Kpis }) {
  const cards: Card[] = [
    {
      label: "Open requests",
      value: kpis.open_requests,
      hint: "Raised and not yet closed",
      href: "/requests",
      Icon: ClipboardList,
    },
    {
      label: "Unfilled IMMEDIATE",
      value: kpis.unfilled_immediate,
      hint: "Life-safety, still awaiting a decision",
      href: "/requests",
      Icon: AlertTriangle,
      urgent: true,
    },
    {
      label: "Sites below reorder",
      value: kpis.sites_below_reorder,
      hint: `${kpis.lines_below_reorder} stock line(s) across these sites`,
      href: "/requests",
      Icon: PackageMinus,
    },
    {
      label: "Pending AI reviews",
      value: kpis.pending_ai_reviews,
      hint: "Recommendations awaiting a human decision",
      href: "/requests",
      Icon: Bot,
      urgent: true,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
      {cards.map((card) => {
        const hot = Boolean(card.urgent && card.value > 0);
        return (
          <Link
            key={card.label}
            href={card.href}
            className={cn(
              "panel flex items-start gap-2.5 p-2.5 transition-colors hover:border-info/50",
              hot && "border-priority/45 bg-priority-dim/25",
            )}
          >
            <card.Icon
              size={15}
              aria-hidden="true"
              className={cn("mt-0.5 shrink-0", hot ? "text-priority" : "text-faint")}
            />
            <div className="min-w-0">
              <div
                className={cn(
                  "text-[22px] font-semibold leading-none tabular-nums",
                  hot ? "text-priority" : "text-ink",
                )}
              >
                {card.value}
              </div>
              <div className="mt-1 text-[11px] font-medium text-ink-2">{card.label}</div>
              <div className="truncate text-[10px] text-faint">{card.hint}</div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
