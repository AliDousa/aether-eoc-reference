"use client";

/**
 * The human-in-the-loop decision surface.
 *
 * An agent has proposed an allocation. Nothing has moved. This card shows the
 * plan, the equity review that shaped it, the sources it cites, and what it
 * does not know — and then offers exactly three actions: approve as proposed,
 * edit and approve, or refuse with a reason.
 *
 * Design decisions worth noting:
 *
 * - The decision controls are ordinary buttons in DOM order, so the whole flow
 *   is keyboard operable without any custom key handling.
 * - "Modify" is not a separate mode toggle hidden behind a menu. Editing a
 *   quantity *is* entering modify mode, because that is what the operator is
 *   actually doing, and the button label changes to say so.
 * - When the operator lacks authority the buttons are disabled AND the reason
 *   is written out. A greyed control with no explanation is a dead end.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  Check,
  ExternalLink,
  Info,
  Loader2,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AiBadge, EquityBadge, RecommendationBadge, ShortfallBadge } from "@/components/ui/badge";
import { ApiError, api } from "@/lib/api";
import { cn, dateTime, pct } from "@/lib/format";
import { Permission, useSession } from "@/lib/session";
import type { Recommendation, ResourceRequest } from "@/lib/types";

export function RecommendationCard({
  request,
  recommendation,
}: {
  request: ResourceRequest;
  recommendation: Recommendation;
}) {
  const { session, canDecide, can } = useSession();
  const queryClient = useQueryClient();

  // `?? []` would allocate a new array each render, invalidating every
  // dependent memo. Memoised so the derived values below stay stable.
  const proposedLegs = useMemo(
    () => recommendation.payload?.legs ?? [],
    [recommendation.payload?.legs],
  );
  const [quantities, setQuantities] = useState<Record<string, number>>(() =>
    Object.fromEntries(proposedLegs.map((leg) => [leg.from_site_id, leg.quantity])),
  );
  const [reason, setReason] = useState("");
  const [overrideEquity, setOverrideEquity] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [violations, setViolations] = useState<Array<{ reason: string; site_name?: string }>>([]);

  const decided = recommendation.status !== "pending";
  const authorised = canDecide(recommendation.agent);
  const isCommander = can(Permission.decideAny);

  const edited = useMemo(
    () =>
      proposedLegs.some((leg) => (quantities[leg.from_site_id] ?? leg.quantity) !== leg.quantity),
    [proposedLegs, quantities],
  );

  const plannedTotal = useMemo(
    () =>
      proposedLegs.reduce((sum, leg) => sum + (quantities[leg.from_site_id] ?? leg.quantity), 0),
    [proposedLegs, quantities],
  );

  const decide = useMutation({
    mutationFn: (decision: "approve" | "modify" | "reject") => {
      setError(null);
      setViolations([]);
      if (decision === "reject") {
        return api.decide(recommendation.id, { decision: "reject", reason });
      }
      const legs = proposedLegs
        .map((leg) => ({
          from_site_id: leg.from_site_id,
          from_site_name: leg.from_site_name,
          quantity: quantities[leg.from_site_id] ?? leg.quantity,
          equity_priority: leg.equity_priority,
        }))
        .filter((leg) => leg.quantity > 0);

      return api.decide(recommendation.id, {
        decision: edited ? "modify" : "approve",
        reason,
        ...(edited ? { modified_legs: legs } : {}),
        ...(overrideEquity ? { override_equity: true } : {}),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
    onError: (cause) => {
      if (cause instanceof ApiError) {
        setError(cause.message);
        const found = cause.detail?.violations;
        if (Array.isArray(found)) {
          setViolations(found as Array<{ reason: string; site_name?: string }>);
        }
      } else {
        setError(cause instanceof Error ? cause.message : "The decision failed.");
      }
    },
  });

  const busy = decide.isPending;
  const equity = recommendation.payload?.equity_review ?? recommendation.equity_review;

  return (
    <section className="panel" aria-label="Agent recommendation">
      <div className="panel-head flex-wrap">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="panel-title">Agent recommendation</h2>
          <AiBadge mode={recommendation.agent_run_id ? undefined : undefined} />
          <RecommendationBadge status={recommendation.status} />
        </div>
        <span className="text-[10px] text-faint">
          confidence {pct(recommendation.confidence)} · {dateTime(recommendation.created_at)}
        </span>
      </div>

      {/* Verify banner — present on every agent output, always. */}
      <p className="flex items-start gap-1.5 border-b border-ai/25 bg-ai-dim px-3 py-1.5 text-[11px] text-ai">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        AI-suggested — verify with current official guidance. Nothing moves until a human approves
        it.
      </p>

      <div className="space-y-3 p-3">
        {/* Plan */}
        <div>
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-widest text-muted">
              Proposed allocation
            </h3>
            <ShortfallBadge
              shortfall={recommendation.payload?.shortfall ?? 0}
              unit={request.sku.unit}
            />
            {equity ? <EquityBadge passed={equity.passed} /> : null}
          </div>

          <div className="scroll-x">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">Source site</th>
                  <th scope="col">Equity</th>
                  <th scope="col">Available</th>
                  <th scope="col">Move</th>
                  <th scope="col">Leaves</th>
                </tr>
              </thead>
              <tbody>
                {proposedLegs.map((leg) => {
                  const value = quantities[leg.from_site_id] ?? leg.quantity;
                  const changed = value !== leg.quantity;
                  return (
                    <tr key={leg.from_site_id}>
                      <td className="text-ink">{leg.from_site_name}</td>
                      <td>
                        <span
                          className={cn(
                            "mono",
                            leg.equity_priority >= 4 ? "text-priority" : "text-faint",
                          )}
                          title={
                            leg.equity_priority >= 4
                              ? "High-need site — protected by the equity floor"
                              : "Reserve or baseline site"
                          }
                        >
                          eq{leg.equity_priority}
                        </span>
                      </td>
                      <td className="tabular-nums text-ink-2">{leg.available_before}</td>
                      <td>
                        {decided ? (
                          <span className="tabular-nums text-ink">{leg.quantity}</span>
                        ) : (
                          <input
                            type="number"
                            min={0}
                            max={leg.available_before}
                            value={value}
                            disabled={!authorised || busy}
                            aria-label={`Quantity from ${leg.from_site_name}`}
                            onChange={(event) =>
                              setQuantities((current) => ({
                                ...current,
                                [leg.from_site_id]: Math.max(0, Number(event.target.value) || 0),
                              }))
                            }
                            className={cn(
                              "field w-24 tabular-nums",
                              changed && "border-priority/60 text-priority",
                            )}
                          />
                        )}
                      </td>
                      <td className="tabular-nums text-faint">{leg.available_before - value}</td>
                    </tr>
                  );
                })}
                {proposedLegs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-4 text-center text-muted">
                      No allocation could be proposed without breaching the equity floor.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <p className="mt-1.5 text-[11.5px] text-ink-2">
            Moving <span className="font-semibold tabular-nums text-ink">{plannedTotal}</span> of{" "}
            <span className="tabular-nums">{request.quantity}</span> {request.sku.unit} to{" "}
            {request.destination_site?.name ?? "the destination"}
            {edited ? (
              <span className="ml-1.5 chip border-priority/40 bg-priority-dim text-priority">
                edited from {recommendation.payload?.allocated_quantity ?? 0}
              </span>
            ) : null}
          </p>
        </div>

        {/* Equity review */}
        {equity ? (
          <div className="rounded border border-line bg-base p-2.5">
            <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-muted">
              {equity.passed ? (
                <ShieldCheck size={12} className="text-ok" aria-hidden="true" />
              ) : (
                <ShieldAlert size={12} className="text-immediate" aria-hidden="true" />
              )}
              Equity review
            </h3>
            <p className="text-[12px] text-ink-2">{equity.summary}</p>
            {equity.withheld?.length > 0 ? (
              <ul className="mt-1.5 space-y-1">
                {equity.withheld.map((item) => (
                  <li key={item.site_id} className="text-[11.5px] text-priority">
                    <span className="font-medium">{item.site_name}:</span> {item.reason}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="mt-1.5 text-[10.5px] text-faint">
              Rule:{" "}
              <Link
                href="/knowledge"
                className="underline decoration-dotted underline-offset-2 hover:text-info"
              >
                {equity.rule_id}
              </Link>
            </p>
          </div>
        ) : null}

        {/* Rationale, notes, uncertainty */}
        {recommendation.rationale ? (
          <details className="rounded border border-line bg-base p-2.5" open>
            <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-widest text-muted">
              Agent rationale
            </summary>
            <p className="mt-1.5 whitespace-pre-line text-[12px] text-ink-2">
              {recommendation.rationale}
            </p>
          </details>
        ) : null}

        {/* Citations */}
        {recommendation.citations?.length > 0 ? (
          <div>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-muted">
              Citations
            </h3>
            <ul className="flex flex-wrap gap-1.5">
              {recommendation.citations.map((citation) => (
                <li key={citation}>
                  <Link
                    href="/knowledge"
                    className="chip border-line bg-panel-2 text-ink-2 hover:border-info/50 hover:text-info"
                    title={citation}
                  >
                    <ExternalLink size={10} aria-hidden="true" />
                    <span className="max-w-[22rem] truncate">{citation}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Decision */}
        {decided ? (
          <div className="rounded border border-line bg-panel-2 p-2.5">
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-muted">
              Human decision
            </h3>
            <p className="text-[12.5px] text-ink">
              <span className="font-semibold">{recommendation.decided_by_name ?? "Unknown"}</span>{" "}
              {recommendation.status === "rejected" ? "rejected" : recommendation.status} this
              recommendation
              {recommendation.decided_at ? ` at ${dateTime(recommendation.decided_at)}` : ""}.
            </p>
            {recommendation.decision_reason ? (
              <p className="mt-1 border-l-2 border-line pl-2 text-[12px] text-ink-2">
                {recommendation.decision_reason}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="rounded border border-line bg-panel-2 p-2.5">
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
              Your decision
            </h3>

            {!session ? (
              <p className="mb-2 flex items-start gap-1.5 text-[12px] text-muted">
                <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                Sign in from the top bar to act on this recommendation.
              </p>
            ) : !authorised ? (
              <p className="mb-2 flex items-start gap-1.5 rounded border border-priority/35 bg-priority-dim p-2 text-[12px] text-priority">
                <ShieldAlert size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>
                  The <strong>{session.operator.ics_role.replace(/_/g, " ")}</strong> does not hold
                  authority to commit resources. Switch to Incident Commander or Logistics to
                  decide. The server enforces this — the buttons below are not the control.
                </span>
              </p>
            ) : null}

            <label className="label" htmlFor="decision-reason">
              Reason {edited ? "(recommended)" : "(required to reject)"}
            </label>
            <textarea
              id="decision-reason"
              className="field mb-2 min-h-[3.5rem] resize-y"
              placeholder="Why are you approving, changing, or refusing this allocation?"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={!authorised || busy}
              maxLength={1000}
            />

            {!equity?.passed && isCommander ? (
              <label className="mb-2 flex items-start gap-2 text-[11.5px] text-priority">
                <input
                  type="checkbox"
                  checked={overrideEquity}
                  onChange={(event) => setOverrideEquity(event.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  Override the equity floor. Incident Commander authority only, and the reason above
                  becomes mandatory. This is recorded in the audit log.
                </span>
              </label>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={!authorised || busy || plannedTotal <= 0}
                onClick={() => decide.mutate(edited ? "modify" : "approve")}
              >
                {busy ? (
                  <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Check size={13} aria-hidden="true" />
                )}
                {edited ? "Modify and approve" : "Approve as recommended"}
              </button>

              <button
                type="button"
                className="btn btn-danger"
                disabled={!authorised || busy || !reason.trim()}
                onClick={() => decide.mutate("reject")}
                title={!reason.trim() ? "A rejection requires a written reason" : undefined}
              >
                <X size={13} aria-hidden="true" />
                Reject
              </button>

              {edited ? (
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() =>
                    setQuantities(
                      Object.fromEntries(
                        proposedLegs.map((leg) => [leg.from_site_id, leg.quantity]),
                      ),
                    )
                  }
                >
                  <RotateCcw size={13} aria-hidden="true" />
                  Reset to proposal
                </button>
              ) : null}
            </div>

            {error ? (
              <div
                role="alert"
                className="mt-2 rounded border border-immediate/40 bg-immediate-dim p-2 text-[12px] text-immediate"
              >
                <p className="flex items-start gap-1.5 font-medium">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
                  {error}
                </p>
                {violations.length > 0 ? (
                  <ul className="mt-1 space-y-0.5 pl-5">
                    {violations.map((violation, index) => (
                      <li key={index} className="list-disc text-[11.5px]">
                        {violation.site_name ? `${violation.site_name}: ` : ""}
                        {violation.reason}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <p className="mt-2 flex items-start gap-1.5 text-[10.5px] text-faint">
              <Bot size={11} className="mt-0.5 shrink-0" aria-hidden="true" />
              Approving writes the stock movement and two audit rows: the decision and the transfer.
              The agent never writes inventory.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
