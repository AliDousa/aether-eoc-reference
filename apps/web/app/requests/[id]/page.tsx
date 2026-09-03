"use client";

/**
 * Request detail: the money path.
 *
 * Shows the request, its state-change timeline drawn straight from the audit
 * log, the agent recommendation, and the human decision controls.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, CircleAlert, Loader2, PackageCheck, Truck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { RecommendationCard } from "@/components/recommendation-card";
import { PriorityBadge, StateBadge } from "@/components/ui/badge";
import { ApiError, api } from "@/lib/api";
import { dateTime, since, titleCase } from "@/lib/format";
import { Permission, useSession } from "@/lib/session";
import type { RequestState } from "@/lib/types";

/** Transitions offered as explicit buttons after an approval. */
const FOLLOW_UP: Partial<Record<RequestState, { label: string; icon: typeof Truck }>> = {
  tasked: { label: "Mark tasked", icon: Truck },
  fulfilled: { label: "Mark fulfilled", icon: PackageCheck },
};

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const queryClient = useQueryClient();
  const { session, can } = useSession();

  const {
    data: request,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["request", id],
    queryFn: () => api.request(id),
    enabled: Boolean(id),
  });

  const recommend = useMutation({
    mutationFn: () => api.recommend(id),
    onSuccess: () => void queryClient.invalidateQueries(),
  });

  const transition = useMutation({
    mutationFn: (target: RequestState) => api.transitionRequest(id, target),
    onSuccess: () => void queryClient.invalidateQueries(),
  });

  if (isLoading) {
    return (
      <p className="flex items-center gap-2 p-6 text-muted">
        <Loader2 size={15} className="animate-spin" aria-hidden="true" />
        Loading request…
      </p>
    );
  }

  if (error || !request) {
    return (
      <div className="panel p-4">
        <p className="text-immediate">Could not load request {id}.</p>
        <Link href="/requests" className="btn mt-2">
          <ArrowLeft size={13} aria-hidden="true" /> Back to requests
        </Link>
      </div>
    );
  }

  const recommendation = request.recommendation;
  const canAskAgent = Boolean(session) && can(Permission.runAgent);
  const needsRecommendation = request.state === "submitted";
  const followUps = request.allowed_transitions.filter(
    (target): target is RequestState => target in FOLLOW_UP,
  );

  return (
    <div className="flex flex-col gap-3">
      <Link href="/requests" className="btn-ghost btn w-fit px-1.5 py-0.5 text-[12px]">
        <ArrowLeft size={13} aria-hidden="true" /> All requests
      </Link>

      {/* Header */}
      <section className="panel p-3" aria-label="Request summary">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <PriorityBadge priority={request.priority} />
              <StateBadge state={request.state} />
              <span className="mono text-faint">{request.id}</span>
            </div>
            <h1 className="text-[16px] font-semibold text-ink">
              {request.quantity} {request.sku.unit} · {request.sku.name}
            </h1>
            <p className="mt-0.5 text-[12px] text-ink-2">
              to {request.destination_site?.name ?? "unassigned"}
              {request.destination_site ? (
                <span className="ml-1 text-faint">
                  (equity priority {request.destination_site.equity_priority} of 5)
                </span>
              ) : null}
            </p>
            <p className="mt-1 text-[11px] text-faint">
              Raised by {request.created_by_name} · {request.requesting_section} ·{" "}
              {since(request.created_at)}
            </p>
          </div>

          <div className="flex flex-col items-end gap-1.5">
            {needsRecommendation ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!canAskAgent || recommend.isPending}
                onClick={() => recommend.mutate()}
                title={canAskAgent ? undefined : "Sign in to run an agent"}
              >
                {recommend.isPending ? (
                  <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Bot size={13} aria-hidden="true" />
                )}
                Ask recommender
              </button>
            ) : null}

            {followUps.map((target) => {
              const meta = FOLLOW_UP[target];
              if (!meta) return null;
              const Icon = meta.icon;
              return (
                <button
                  key={target}
                  type="button"
                  className="btn"
                  disabled={!can(Permission.submitRequest) || transition.isPending}
                  onClick={() => transition.mutate(target)}
                >
                  <Icon size={13} aria-hidden="true" />
                  {meta.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-2 border-t border-line-soft pt-2">
          <h2 className="label">Justification</h2>
          <p className="text-[12.5px] text-ink-2">{request.justification}</p>
        </div>

        {recommend.isError ? (
          <p
            role="alert"
            className="mt-2 flex items-center gap-1.5 rounded border border-immediate/40 bg-immediate-dim p-2 text-[12px] text-immediate"
          >
            <CircleAlert size={13} aria-hidden="true" />
            {recommend.error instanceof ApiError
              ? recommend.error.message
              : "Could not run the recommender."}
          </p>
        ) : null}
        {transition.isError ? (
          <p
            role="alert"
            className="mt-2 flex items-center gap-1.5 rounded border border-immediate/40 bg-immediate-dim p-2 text-[12px] text-immediate"
          >
            <CircleAlert size={13} aria-hidden="true" />
            {transition.error instanceof ApiError
              ? transition.error.message
              : "That transition is not allowed."}
          </p>
        ) : null}
      </section>

      <div className="grid gap-3 xl:grid-cols-[1.5fr_1fr]">
        <div className="flex flex-col gap-3">
          {recommendation ? (
            <RecommendationCard request={request} recommendation={recommendation} />
          ) : (
            <section className="panel p-4 text-center">
              <Bot size={20} className="mx-auto mb-2 text-faint" aria-hidden="true" />
              <p className="text-[13px] text-ink-2">No recommendation yet.</p>
              <p className="mt-1 text-[11.5px] text-faint">
                Use <strong>Ask recommender</strong> to generate an allocation proposal. It will not
                move any stock.
              </p>
            </section>
          )}
        </div>

        {/* Timeline straight from the audit log */}
        <section className="panel" aria-label="State change timeline">
          <div className="panel-head">
            <h2 className="panel-title">Timeline</h2>
            <span className="text-[10px] text-faint">from the audit log</span>
          </div>
          <ol className="divide-y divide-line-soft">
            {(request.timeline ?? []).map((entry) => (
              <li key={entry.seq} className="px-3 py-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[12.5px] font-medium text-ink">
                    {titleCase(entry.action.replace(/^request\./, ""))}
                  </span>
                  <span className="mono shrink-0 text-faint">#{entry.seq}</span>
                </div>
                <p className="text-[11px] text-muted">
                  {entry.actor} · {dateTime(entry.at)}
                </p>
                {entry.ai_trace_id ? (
                  <p className="mono mt-0.5 text-[10px] text-ai">trace {entry.ai_trace_id}</p>
                ) : null}
              </li>
            ))}
            {(request.timeline ?? []).length === 0 ? (
              <li className="px-3 py-4 text-center text-[12px] text-muted">
                No audit entries yet.
              </li>
            ) : null}
          </ol>
          <div className="border-t border-line px-3 py-2">
            <Link
              href={{ pathname: "/audit", query: { entity: request.id } }}
              className="text-[11.5px] text-info underline decoration-dotted underline-offset-2"
            >
              Open in audit log →
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
