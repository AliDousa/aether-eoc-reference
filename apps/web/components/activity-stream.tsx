"use client";

/**
 * The incident log.
 *
 * Posting is optimistic: the note appears immediately, marked as unconfirmed,
 * and is replaced when the server's copy arrives. If the write fails the
 * optimistic entry is removed and the text is returned to the box so nothing
 * the operator typed is lost.
 *
 * The server remains the source of truth throughout — the optimistic row is
 * visibly distinct (dashed, "sending") and never counted as logged until it
 * comes back from the API.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  FileText,
  Loader2,
  PackageCheck,
  Send,
  Truck,
  UserCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { clockTime, cn, since } from "@/lib/format";
import { Permission, useSession } from "@/lib/session";
import type { ActivityEvent } from "@/lib/types";

const KIND_META: Record<string, { Icon: LucideIcon; tint: string; label: string }> = {
  log_note: { Icon: FileText, tint: "text-muted", label: "Log note" },
  status_change: { Icon: CheckCircle2, tint: "text-info", label: "Status change" },
  resource_request: { Icon: Send, tint: "text-priority", label: "Resource request" },
  resource_movement: { Icon: Truck, tint: "text-ok", label: "Resource movement" },
  agent_output: { Icon: Bot, tint: "text-ai", label: "Agent output" },
  human_decision: { Icon: UserCheck, tint: "text-ok", label: "Human decision" },
};

interface OptimisticNote {
  tempId: string;
  body: string;
  createdAt: string;
}

export function ActivityStream({
  events,
  incidentId,
}: {
  events: ActivityEvent[];
  incidentId: string;
}) {
  const { session, can } = useSession();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<OptimisticNote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const canPost = Boolean(session) && can(Permission.postActivity);

  // Reconciliation is derived during render, not synchronised in an effect:
  // a note whose text has already come back from the server is simply not
  // drawn as pending. This keeps the confirmed list and the optimistic list
  // consistent without a cascading setState.
  const confirmedBodies = useMemo(() => new Set(events.map((event) => event.body)), [events]);
  const visiblePending = pending.filter((note) => !confirmedBodies.has(note.body));

  const post = useMutation({
    mutationFn: (variables: OptimisticNote) => api.postNote(incidentId, variables.body),
    onError: (cause, variables) => {
      setPending((current) => current.filter((note) => note.tempId !== variables.tempId));
      setDraft(variables.body); // give the operator their text back
      setError(cause instanceof Error ? cause.message : "Could not post the note.");
    },
    onSuccess: (_data, variables) => {
      setError(null);
      setPending((current) => current.filter((note) => note.tempId !== variables.tempId));
      void queryClient.invalidateQueries({ queryKey: ["board"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || !canPost) return;
    const note: OptimisticNote = {
      tempId: `tmp_${Date.now()}`,
      body,
      createdAt: new Date().toISOString(),
    };
    setPending((current) => [note, ...current]);
    setDraft("");
    post.mutate(note);
  };

  return (
    <section className="panel flex min-h-0 flex-col" aria-label="Activity stream">
      <div className="panel-head">
        <h2 className="panel-title">Activity stream</h2>
        <span className="text-[10px] text-faint">{events.length} entries · append-only</span>
      </div>

      <form onSubmit={submit} className="flex gap-1.5 border-b border-line px-2.5 py-2">
        <input
          ref={inputRef}
          className="field"
          placeholder={
            canPost ? "Post a log note to the incident…" : "Sign in as any role to post a note"
          }
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={!canPost}
          aria-label="New log note"
          maxLength={2000}
        />
        <button type="submit" className="btn btn-primary" disabled={!canPost || !draft.trim()}>
          <Send size={12} aria-hidden="true" />
          Post
        </button>
      </form>

      {error ? (
        <p
          role="alert"
          className="flex items-center gap-1.5 border-b border-immediate/30 bg-immediate-dim px-2.5 py-1.5 text-[11px] text-immediate"
        >
          <CircleAlert size={12} aria-hidden="true" />
          {error}
        </p>
      ) : null}

      <ol className="min-h-0 flex-1 divide-y divide-line-soft overflow-y-auto">
        {visiblePending.map((note) => (
          <li
            key={note.tempId}
            className="flex gap-2 border-l-2 border-dashed border-info/60 px-2.5 py-2 opacity-70"
          >
            <Loader2
              size={13}
              className="mt-0.5 shrink-0 animate-spin text-info"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-[12.5px] text-ink-2">{note.body}</p>
              <p className="text-[10px] text-faint">Sending — not yet confirmed by the server</p>
            </div>
          </li>
        ))}

        {events.map((event) => {
          const meta = KIND_META[event.kind] ?? {
            Icon: PackageCheck,
            tint: "text-muted",
            label: event.kind,
          };
          return (
            <li key={event.id} className="flex gap-2 px-2.5 py-2 hover:bg-panel-2">
              <meta.Icon
                size={13}
                aria-hidden="true"
                className={cn("mt-0.5 shrink-0", meta.tint)}
              />
              <div className="min-w-0 flex-1">
                <p className="break-words text-[12.5px] text-ink">{event.body}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10px] text-faint">
                  <span className="font-medium text-muted">{event.actor_name}</span>
                  <span title={event.created_at}>{clockTime(event.created_at)}</span>
                  <span>{since(event.created_at)}</span>
                  <span className="uppercase tracking-wider">{meta.label}</span>
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
