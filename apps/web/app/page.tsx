"use client";

/**
 * Incident board — the landing screen.
 *
 * Header, KPIs, ICS section chips, the live activity stream, the request
 * queue, and a stock-by-site chart. Everything visible here is seeded, so a
 * clone is never greeted by an empty state.
 */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Target } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { KpiCards } from "@/components/kpi-cards";
import { ActivityStream } from "@/components/activity-stream";
import { RequestsTable } from "@/components/requests-table";
import type { ViewRole } from "@/components/requests-table";
import { api } from "@/lib/api";
import { cn, dateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { InventoryPosition } from "@/lib/types";

const VIEW_ROLES: Array<{ value: ViewRole; label: string }> = [
  { value: "incident_commander", label: "Incident Commander" },
  { value: "operations_section", label: "Operations" },
  { value: "logistics_section", label: "Logistics" },
];

export default function BoardPage() {
  const { session } = useSession();
  const [overrideRole, setOverrideRole] = useState<ViewRole | null>(null);

  const { data: board, isLoading, error } = useQuery({ queryKey: ["board"], queryFn: api.board });

  // The view follows the signed-in role unless explicitly overridden, so
  // switching role in the top bar also re-orders the queue.
  const sessionRole = session?.operator.ics_role;
  const viewRole: ViewRole =
    overrideRole ??
    (sessionRole === "incident_commander" ||
    sessionRole === "operations_section" ||
    sessionRole === "logistics_section"
      ? sessionRole
      : "incident_commander");

  const chartData = useMemo(() => buildStockChart(board?.inventory ?? []), [board?.inventory]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-8 text-muted">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        Loading incident board…
      </div>
    );
  }

  if (error || !board) {
    return (
      <div className="panel p-4">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-immediate">
          <AlertTriangle size={15} aria-hidden="true" />
          Board unavailable
        </h2>
        <p className="text-[12.5px] text-ink-2">
          The API did not return an incident. Start it with{" "}
          <code className="mono rounded bg-base px-1">make dev-api</code> and seed the scenario with{" "}
          <code className="mono rounded bg-base px-1">make seed</code>.
        </p>
        {error ? <p className="mt-2 text-[11px] text-faint">{String(error)}</p> : null}
      </div>
    );
  }

  const openRequests = board.requests.filter((request) => request.is_open);

  return (
    <div className="flex flex-col gap-3">
      {/* Incident header */}
      <section className="panel p-3" aria-label="Incident summary">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-ink">{board.incident.name}</h2>
            <p className="mt-0.5 text-[12px] text-ink-2">{board.incident.type}</p>
            <p className="mt-1 text-[11px] text-faint">
              Activated {dateTime(board.incident.activated_at)} · Commander{" "}
              <span className="text-muted">{board.incident.commander?.display_name ?? "—"}</span> ·{" "}
              {board.incident.jurisdiction}
            </p>
          </div>

          {/* ICS section chips: presence only, per the slice scope. */}
          <ul className="flex flex-wrap gap-1.5" aria-label="ICS sections">
            {board.sections.map((section) => (
              <li
                key={section.section}
                className={cn(
                  "chip",
                  section.implemented
                    ? "border-line bg-panel-2 text-ink-2"
                    : "border-dashed border-line bg-base text-faint",
                )}
                title={
                  section.implemented
                    ? `${section.operator_count} operator(s) assigned`
                    : "Present in the ICS structure but not implemented in this reference slice"
                }
              >
                {section.label}
                <span className="text-faint">
                  {section.implemented ? section.operator_count : "n/i"}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {board.incident.objectives.length > 0 ? (
          <details className="mt-2 border-t border-line-soft pt-2">
            <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-widest text-muted">
              Incident objectives ({board.incident.objectives.length})
            </summary>
            <ul className="mt-1.5 space-y-1">
              {board.incident.objectives.map((objective) => (
                <li key={objective} className="flex gap-1.5 text-[12px] text-ink-2">
                  <Target size={12} className="mt-0.5 shrink-0 text-faint" aria-hidden="true" />
                  {objective}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <KpiCards kpis={board.kpis} />

      <div className="grid min-h-0 gap-3 xl:grid-cols-[1.15fr_1fr]">
        {/* Requests */}
        <section className="panel flex min-h-0 flex-col" aria-label="Resource requests">
          <div className="panel-head flex-wrap">
            <h2 className="panel-title">Resource requests</h2>
            <div className="flex items-center gap-1" role="group" aria-label="View as role">
              <span className="text-[10px] uppercase tracking-widest text-faint">View as</span>
              {VIEW_ROLES.map((role) => (
                <button
                  key={role.value}
                  type="button"
                  onClick={() => setOverrideRole(role.value)}
                  aria-pressed={viewRole === role.value}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[10.5px] transition-colors",
                    viewRole === role.value
                      ? "border-info/50 bg-info-dim font-semibold text-info"
                      : "border-line bg-base text-muted hover:text-ink",
                  )}
                >
                  {role.label}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <RequestsTable
              requests={board.requests}
              viewRole={viewRole}
              caption="Resource requests for this incident"
            />
          </div>
          <p className="border-t border-line px-2.5 py-1.5 text-[10.5px] text-faint">
            {openRequests.length} open of {board.requests.length} · column order follows the
            selected role; the rows are identical
          </p>
        </section>

        {/* Activity */}
        <div className="min-h-0 xl:max-h-[calc(100vh-22rem)]">
          <ActivityStream events={board.activity} incidentId={board.incident.id} />
        </div>
      </div>

      {/* Stock */}
      <section className="panel" aria-label="Stock under contention">
        <div className="panel-head">
          <h2 className="panel-title">Stock by site — items under contention</h2>
          <span className="text-[10px] text-faint">
            {board.below_reorder.length} line(s) below reorder point
          </span>
        </div>
        <div className="p-3">
          {chartData.length > 0 ? (
            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "#8798ad", fontSize: 10 }}
                    axisLine={{ stroke: "#253243" }}
                    tickLine={false}
                    interval={0}
                    angle={-12}
                    textAnchor="end"
                    height={48}
                  />
                  <YAxis
                    tick={{ fill: "#8798ad", fontSize: 10 }}
                    axisLine={{ stroke: "#253243" }}
                    tickLine={false}
                    width={34}
                  />
                  <Tooltip
                    cursor={{ fill: "#16202d" }}
                    contentStyle={{
                      background: "#111823",
                      border: "1px solid #253243",
                      borderRadius: 4,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "#e8eef5" }}
                    formatter={(value, _name, item) => {
                      // Recharts types the payload loosely; the rows are ours.
                      const row = item?.payload as ChartRow | undefined;
                      return [
                        `${Number(value ?? 0)} available (reorder ${row?.reorder ?? 0})`,
                        "Stock",
                      ];
                    }}
                  />
                  <Bar dataKey="available" radius={[2, 2, 0, 0]}>
                    {chartData.map((row) => (
                      <Cell key={row.label} fill={row.below ? "#f2b53c" : "#5aa9e6"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-[12px] text-muted">No inventory positions loaded.</p>
          )}
          <p className="mt-1 text-[10.5px] text-faint">
            Amber bars are below their reorder point. Values are available stock (on hand minus
            reserved).
          </p>
        </div>
      </section>
    </div>
  );
}

interface ChartRow {
  label: string;
  available: number;
  reorder: number;
  below: boolean;
}

/**
 * Charting every SKU at every site would be forty bars of noise. Show the
 * items that are actually contested: anything below reorder, plus the ORS
 * line the scenario turns on.
 */
function buildStockChart(positions: InventoryPosition[]): ChartRow[] {
  const interesting = positions.filter(
    (position) => position.below_reorder || position.sku_code === "ORS-KIT",
  );
  return interesting
    .slice(0, 12)
    .map((position) => ({
      label: `${position.sku_code} · ${position.site_name.replace(/ (Cooling Center|Cache|Staging)$/, "")}`,
      available: position.available,
      reorder: position.reorder_point,
      below: position.below_reorder,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
