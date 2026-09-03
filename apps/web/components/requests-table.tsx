"use client";

/**
 * Resource request queue.
 *
 * Role changes emphasis, not data. Everyone sees every request — hiding rows
 * from an operator on a shared incident board causes more problems than it
 * solves. What changes is which columns lead and what gets highlighted:
 *
 *   Incident Commander  decisions awaiting authority, and shortfalls
 *   Logistics           source sites, stock, and what needs tasking
 *   Operations          what they asked for and where it has got to
 */

import { ArrowUpRight, Bot } from "lucide-react";
import Link from "next/link";

import { PriorityBadge, StateBadge } from "@/components/ui/badge";
import { cn, since } from "@/lib/format";
import type { IcsRole, ResourceRequest } from "@/lib/types";

export type ViewRole = Extract<
  IcsRole,
  "incident_commander" | "operations_section" | "logistics_section"
>;

type ColumnKey =
  | "priority"
  | "item"
  | "quantity"
  | "destination"
  | "state"
  | "requested_by"
  | "section"
  | "shortfall"
  | "age";

const COLUMN_LABEL: Record<ColumnKey, string> = {
  priority: "Priority",
  item: "Item",
  quantity: "Qty",
  destination: "Destination",
  state: "State",
  requested_by: "Raised by",
  section: "Section",
  shortfall: "Short",
  age: "Age",
};

/** Column order per role. Same rows, different reading order. */
const ROLE_COLUMNS: Record<ViewRole, ColumnKey[]> = {
  incident_commander: ["priority", "state", "item", "quantity", "shortfall", "destination", "age"],
  logistics_section: ["priority", "item", "quantity", "shortfall", "destination", "state", "age"],
  operations_section: [
    "priority",
    "item",
    "quantity",
    "destination",
    "state",
    "requested_by",
    "age",
  ],
};

function shortfallOf(request: ResourceRequest): number | null {
  const payload = request.recommendation?.payload;
  if (!payload) return null;
  return payload.shortfall ?? null;
}

export function RequestsTable({
  requests,
  viewRole,
  caption,
}: {
  requests: ResourceRequest[];
  viewRole: ViewRole;
  caption?: string;
}) {
  const columns = ROLE_COLUMNS[viewRole];

  return (
    <div className="scroll-x">
      <table className="tbl">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((key) => (
              <th key={key} scope="col">
                {COLUMN_LABEL[key]}
              </th>
            ))}
            <th scope="col" className="w-8">
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {requests.map((request) => {
            const shortfall = shortfallOf(request);
            const needsDecision = request.recommendation?.status === "pending";
            return (
              <tr key={request.id} className={cn(needsDecision && "bg-ai-dim/30")}>
                {columns.map((key) => (
                  <td key={key}>{renderCell(key, request, shortfall)}</td>
                ))}
                <td>
                  <Link
                    href={`/requests/${request.id}`}
                    className="btn-ghost btn px-1.5 py-0.5"
                    aria-label={`Open request ${request.id}`}
                  >
                    <ArrowUpRight size={13} aria-hidden="true" />
                  </Link>
                </td>
              </tr>
            );
          })}
          {requests.length === 0 ? (
            <tr>
              <td colSpan={columns.length + 1} className="py-6 text-center text-muted">
                No requests match this filter.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function renderCell(
  key: ColumnKey,
  request: ResourceRequest,
  shortfall: number | null,
): React.ReactNode {
  switch (key) {
    case "priority":
      return <PriorityBadge priority={request.priority} />;
    case "item":
      return (
        <span className="block max-w-[15rem] truncate text-ink" title={request.sku.name}>
          {request.sku.name}
          <span className="mono ml-1.5 text-faint">{request.sku.code}</span>
        </span>
      );
    case "quantity":
      return (
        <span className="tabular-nums text-ink">
          {request.quantity}
          <span className="ml-1 text-faint">{request.sku.unit}</span>
        </span>
      );
    case "destination":
      return (
        <span className="text-ink-2">
          {request.destination_site?.name ?? "—"}
          {request.destination_site ? (
            <span
              className="ml-1.5 text-[10px] text-faint"
              title={`Equity priority ${request.destination_site.equity_priority} of 5`}
            >
              eq{request.destination_site.equity_priority}
            </span>
          ) : null}
        </span>
      );
    case "state":
      return (
        <span className="flex flex-wrap items-center gap-1">
          <StateBadge state={request.state} />
          {request.recommendation?.status === "pending" ? (
            <span
              className="chip border-ai/40 bg-ai-dim text-ai"
              title="An agent proposal is waiting"
            >
              <Bot size={11} aria-hidden="true" />
              Needs decision
            </span>
          ) : null}
        </span>
      );
    case "requested_by":
      return <span className="text-ink-2">{request.created_by_name}</span>;
    case "section":
      return <span className="text-ink-2 capitalize">{request.requesting_section}</span>;
    case "shortfall":
      if (shortfall === null) return <span className="text-faint">—</span>;
      return shortfall > 0 ? (
        <span className="font-semibold tabular-nums text-priority">{shortfall}</span>
      ) : (
        <span className="tabular-nums text-ok">0</span>
      );
    case "age":
      return (
        <span className="whitespace-nowrap text-faint" title={request.created_at}>
          {since(request.created_at)}
        </span>
      );
    default:
      return null;
  }
}
