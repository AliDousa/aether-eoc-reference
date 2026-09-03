"use client";

/**
 * Audit log.
 *
 * Filterable table plus a JSON diff drawer. The chain verification strip at the
 * top is the point of the page: it replays every row from genesis and says
 * whether the log has been altered.
 *
 * The quick filters match the demo script — `ai.*` and `inventory.*` — because
 * the interesting claim is that an AI suggestion, a human decision, and a stock
 * movement all appear in one unbroken sequence.
 */

import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  Link2,
  Loader2,
  Package,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { api } from "@/lib/api";
import { cn, dateTime, shortHash } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";

const QUICK_FILTERS: Array<{ label: string; prefix: string; hint: string }> = [
  { label: "All", prefix: "", hint: "Every audited action" },
  { label: "ai.*", prefix: "ai.", hint: "Every agent invocation" },
  { label: "inventory.*", prefix: "inventory.", hint: "Every stock movement" },
  { label: "recommendation.*", prefix: "recommendation.", hint: "Every human decision" },
  { label: "request.*", prefix: "request.", hint: "Every request state change" },
  { label: "activity.*", prefix: "activity.", hint: "Log notes posted by operators" },
  { label: "auth.*", prefix: "auth.", hint: "Sign-ins" },
];

export default function AuditPage() {
  return (
    <Suspense fallback={<p className="p-6 text-muted">Loading audit log…</p>}>
      <AuditView />
    </Suspense>
  );
}

function AuditView() {
  const searchParams = useSearchParams();
  const entityFromUrl = searchParams.get("entity") ?? "";

  const [prefix, setPrefix] = useState("");
  // The URL supplies the initial entity filter (the request detail page links
  // here with ?entity=). A local edit takes precedence once the operator types.
  // Derived rather than synchronised in an effect, so there is no render cascade.
  const [entityOverride, setEntityOverride] = useState<string | null>(null);
  const entityId = entityOverride ?? entityFromUrl;
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["audit", prefix, entityId],
    queryFn: () =>
      api.audit({
        action_prefix: prefix || undefined,
        entity_id: entityId || undefined,
        limit: 200,
      }),
  });

  const { data: chain } = useQuery({ queryKey: ["audit", "verify"], queryFn: api.verifyChain });

  return (
    <div className="flex flex-col gap-3">
      {/* Chain verification */}
      <section
        className={cn(
          "panel flex flex-wrap items-center justify-between gap-3 p-3",
          chain?.ok === false && "border-immediate/50",
        )}
        aria-label="Audit chain verification"
      >
        <div className="flex items-start gap-2">
          {chain?.ok ? (
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-ok" aria-hidden="true" />
          ) : (
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-immediate" aria-hidden="true" />
          )}
          <div>
            <h1 className="text-[14px] font-semibold text-ink">
              {chain?.ok ? "Audit chain verified" : "Audit chain BROKEN"}
            </h1>
            <p className="text-[11.5px] text-ink-2">
              {chain?.detail ?? "Verifying…"}
              {chain?.broken_at_seq ? ` (first divergence at row ${chain.broken_at_seq})` : ""}
            </p>
          </div>
        </div>
        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
          <div>
            <dt className="text-[10px] uppercase tracking-widest text-faint">Rows</dt>
            <dd className="tabular-nums text-ink">{chain?.checked ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-widest text-faint">Head hash</dt>
            <dd className="mono text-ink-2">{shortHash(chain?.head_hash ?? "", 16)}</dd>
          </div>
        </dl>
      </section>

      {/* Filters */}
      <section className="panel p-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-widest text-faint">Action</span>
          {QUICK_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              aria-pressed={prefix === filter.prefix}
              title={filter.hint}
              onClick={() => setPrefix(filter.prefix)}
              className={cn(
                "mono rounded border px-1.5 py-0.5 text-[11px] transition-colors",
                prefix === filter.prefix
                  ? "border-info/50 bg-info-dim font-semibold text-info"
                  : "border-line bg-base text-muted hover:text-ink",
              )}
            >
              {filter.label}
            </button>
          ))}

          <div className="ml-auto flex items-center gap-1.5">
            <label className="text-[10px] uppercase tracking-widest text-faint" htmlFor="entity">
              Entity id
            </label>
            <input
              id="entity"
              className="field mono w-44 py-0.5"
              placeholder="req_… / rec_…"
              value={entityId}
              onChange={(event) => setEntityOverride(event.target.value.trim())}
            />
            {entityId ? (
              <button
                type="button"
                className="btn-ghost btn px-1 py-0.5"
                onClick={() => setEntityOverride("")}
                aria-label="Clear entity filter"
              >
                <X size={12} aria-hidden="true" />
              </button>
            ) : null}
          </div>
        </div>

        {data?.action_counts?.length ? (
          <p className="mt-1.5 flex flex-wrap gap-x-3 text-[10.5px] text-faint">
            {data.action_counts.map((row) => (
              <span key={row.action} className="mono">
                {row.action}
                <span className="ml-1 text-muted">{row.count}</span>
              </span>
            ))}
          </p>
        ) : null}
      </section>

      <div className="grid gap-3 xl:grid-cols-[1.6fr_1fr]">
        {/* Table */}
        <section className="panel" aria-label="Audit events">
          <div className="panel-head">
            <h2 className="panel-title">Audit events</h2>
            <span className="text-[10px] text-faint">
              {isLoading ? "loading…" : `${data?.events.length ?? 0} of ${data?.total ?? 0}`}
            </span>
          </div>
          <div className="scroll-x max-h-[calc(100vh-20rem)] overflow-y-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Time</th>
                  <th scope="col">Action</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Chain</th>
                  <th scope="col" className="w-8">
                    <span className="sr-only">Inspect</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {(data?.events ?? []).map((event) => (
                  <tr key={event.id} className={cn(selected?.id === event.id && "bg-info-dim/40")}>
                    <td className="mono tabular-nums text-faint">{event.seq}</td>
                    <td className="whitespace-nowrap text-ink-2">{dateTime(event.at)}</td>
                    <td>
                      <span className="flex items-center gap-1.5">
                        <ActionIcon action={event.action} />
                        <span className="mono text-ink">{event.action}</span>
                      </span>
                    </td>
                    <td className="text-ink-2">{event.actor_label}</td>
                    <td className="mono text-faint">{event.entity_id}</td>
                    <td className="mono text-faint" title={`hash ${event.hash}`}>
                      {shortHash(event.hash, 8)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn-ghost btn px-1 py-0.5"
                        onClick={() => setSelected(event)}
                        aria-label={`Inspect audit row ${event.seq}`}
                      >
                        <ChevronRight size={13} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-muted">
                      <Loader2 size={15} className="mx-auto animate-spin" aria-hidden="true" />
                    </td>
                  </tr>
                ) : null}
                {!isLoading && (data?.events.length ?? 0) === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-muted">
                      No audit rows match this filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        {/* Diff drawer */}
        <DiffDrawer event={selected} onClose={() => setSelected(null)} />
      </div>
    </div>
  );
}

function ActionIcon({ action }: { action: string }) {
  if (action.startsWith("ai.")) return <Bot size={12} className="text-ai" aria-hidden="true" />;
  if (action.startsWith("inventory."))
    return <Package size={12} className="text-ok" aria-hidden="true" />;
  if (action.startsWith("recommendation."))
    return <CheckCircle2 size={12} className="text-info" aria-hidden="true" />;
  return <Link2 size={12} className="text-faint" aria-hidden="true" />;
}

function DiffDrawer({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  if (!event) {
    return (
      <section className="panel p-4 text-center" aria-label="Audit detail">
        <p className="text-[12.5px] text-muted">Select a row to inspect its before/after state.</p>
        <p className="mt-1 text-[11px] text-faint">
          Each row commits to the one before it, so altering history breaks verification for every
          row after it.
        </p>
      </section>
    );
  }

  return (
    <section className="panel flex flex-col" aria-label="Audit detail">
      <div className="panel-head">
        <h2 className="panel-title">Row #{event.seq}</h2>
        <button
          type="button"
          className="btn-ghost btn px-1 py-0.5"
          onClick={onClose}
          aria-label="Close"
        >
          <X size={13} aria-hidden="true" />
        </button>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-b border-line px-3 py-2 text-[11.5px]">
        <dt className="text-faint">Action</dt>
        <dd className="mono text-ink">{event.action}</dd>
        <dt className="text-faint">Actor</dt>
        <dd className="text-ink-2">{event.actor_label}</dd>
        <dt className="text-faint">Entity</dt>
        <dd className="mono text-ink-2">
          {event.entity_type} · {event.entity_id}
        </dd>
        <dt className="text-faint">Correlation</dt>
        <dd className="mono text-ink-2">{event.correlation_id}</dd>
        {event.ai_trace_id ? (
          <>
            <dt className="text-faint">AI trace</dt>
            <dd className="mono text-ai">{event.ai_trace_id}</dd>
          </>
        ) : null}
        <dt className="text-faint">Prev hash</dt>
        <dd className="mono break-all text-faint">{event.prev_hash}</dd>
        <dt className="text-faint">Hash</dt>
        <dd className="mono break-all text-ink-2">{event.hash}</dd>
      </dl>

      <div className="grid min-h-0 flex-1 gap-2 overflow-y-auto p-3 md:grid-cols-2">
        <JsonBlock title="Before" value={event.before} tone="before" />
        <JsonBlock title="After" value={event.after} tone="after" />
      </div>
    </section>
  );
}

function JsonBlock({
  title,
  value,
  tone,
}: {
  title: string;
  value: Record<string, unknown> | null;
  tone: "before" | "after";
}) {
  return (
    <div className="min-w-0">
      <h3
        className={cn(
          "mb-1 text-[10px] font-semibold uppercase tracking-widest",
          tone === "before" ? "text-faint" : "text-ok",
        )}
      >
        {title}
      </h3>
      <pre
        className={cn(
          "mono max-h-72 overflow-auto rounded border p-2 text-[10.5px] leading-relaxed",
          tone === "before"
            ? "border-line bg-base text-muted"
            : "border-ok/25 bg-ok-dim/30 text-ink-2",
        )}
      >
        {value ? JSON.stringify(value, null, 2) : "null"}
      </pre>
    </div>
  );
}
