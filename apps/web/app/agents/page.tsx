"use client";

/**
 * Agents page.
 *
 * Three things, in this order: what each agent will and will not do, a place to
 * run the two advisory agents, and the run history with its trace.
 *
 * The "will not" column is deliberately given equal weight to "will". For an
 * operational tool, the boundary is the specification.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Info,
  Loader2,
  Play,
  Search,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { AiBadge } from "@/components/ui/badge";
import { ApiError, api } from "@/lib/api";
import { cn, dateTime, pct } from "@/lib/format";
import { Permission, useSession } from "@/lib/session";
import type { AgentResultPayload } from "@/lib/types";

const SUGGESTED_QUESTIONS = [
  "When do we open a second cooling center?",
  "How much ORS should we plan per occupant per hour?",
  "May an automated system override the equity floor?",
  "What must a SITREP say about information gaps?",
];

export default function AgentsPage() {
  const { session, can } = useSession();
  const [question, setQuestion] = useState(SUGGESTED_QUESTIONS[0] ?? "");
  const [result, setResult] = useState<AgentResultPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    data: catalogue,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["agents"],
    queryFn: api.agents,
  });

  const canRun = Boolean(session) && can(Permission.runAgent);

  const run = useMutation({
    mutationFn: (payload: { intent: string; question?: string }) => api.runAgent(payload),
    onSuccess: (data) => {
      setResult(data.result);
      setError(null);
      void refetch();
    },
    onError: (cause) => {
      setResult(null);
      setError(cause instanceof ApiError ? cause.message : "The agent run failed.");
    },
  });

  return (
    <div className="flex flex-col gap-3">
      {/* Mode */}
      <section className="panel p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-[15px] font-semibold text-ink">Agent orchestration</h1>
            <p className="text-[12px] text-ink-2">
              A supervisor routes an intent to exactly one specialist. Specialists never call each
              other, and none of them can write inventory.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <AiBadge mode={catalogue?.mode} />
            <span className="mono text-[11px] text-faint">
              {catalogue?.model_id ?? "deterministic-rules-v1"}
            </span>
          </div>
        </div>

        {catalogue && !catalogue.llm_enabled ? (
          <p className="mt-2 flex items-start gap-1.5 rounded border border-line bg-base p-2 text-[11.5px] text-muted">
            <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              Running in <strong className="text-ink-2">deterministic fixture mode</strong> — no
              model is configured, and none is needed. Every output below is derived from rules and
              the bundled corpus. Setting <code className="mono">LLM_PROVIDER</code> and{" "}
              <code className="mono">LLM_API_KEY</code> lets the two narrative agents write their
              prose with a model instead; the recommender stays deterministic either way.
            </span>
          </p>
        ) : null}
      </section>

      {/* Specs */}
      <div className="grid gap-2.5 lg:grid-cols-3">
        {(catalogue?.agents ?? []).map((agent) => (
          <section key={agent.name} className="panel flex flex-col p-3">
            <div className="mb-1.5 flex items-start justify-between gap-2">
              <h2 className="text-[13px] font-semibold text-ink">{agent.label}</h2>
              {agent.requires_human ? (
                <span
                  className="chip border-ai/40 bg-ai-dim text-ai"
                  title="Output is held for a human decision"
                >
                  <ShieldAlert size={11} aria-hidden="true" />
                  HITL
                </span>
              ) : (
                <span className="chip border-line bg-panel-2 text-muted">Advisory</span>
              )}
            </div>
            <p className="mb-2 text-[12px] text-ink-2">{agent.purpose}</p>

            <dl className="mt-auto space-y-1.5 text-[11.5px]">
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-faint">Will</dt>
                <dd>
                  <ul className="mt-0.5 space-y-0.5">
                    {agent.will.map((item) => (
                      <li key={item} className="flex gap-1.5 text-ok">
                        <CheckCircle2 size={11} className="mt-0.5 shrink-0" aria-hidden="true" />
                        <span className="text-ink-2">{item}</span>
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-widest text-faint">Will not</dt>
                <dd>
                  <ul className="mt-0.5 space-y-0.5">
                    {agent.will_not.map((item) => (
                      <li key={item} className="flex gap-1.5">
                        <XCircle
                          size={11}
                          className="mt-0.5 shrink-0 text-immediate"
                          aria-hidden="true"
                        />
                        <span className="text-ink-2">{item}</span>
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            </dl>
          </section>
        ))}
      </div>

      {/* Run */}
      <section className="panel p-3">
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
          Run an agent
        </h2>

        {!canRun ? (
          <p className="mb-2 flex items-center gap-1.5 text-[12px] text-muted">
            <Info size={12} aria-hidden="true" />
            Sign in from the top bar to run an agent. Any role may.
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canRun || run.isPending}
            onClick={() => run.mutate({ intent: "situation_summary" })}
          >
            {run.isPending && run.variables?.intent === "situation_summary" ? (
              <Loader2 size={13} className="animate-spin" aria-hidden="true" />
            ) : (
              <Play size={13} aria-hidden="true" />
            )}
            Run situation summary
          </button>
        </div>

        <div className="mt-3 border-t border-line-soft pt-3">
          <label className="label" htmlFor="protocol-question">
            Ask the protocol retriever
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              id="protocol-question"
              className="field flex-1 min-w-[16rem]"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a protocol question…"
              disabled={!canRun}
            />
            <button
              type="button"
              className="btn"
              disabled={!canRun || run.isPending || !question.trim()}
              onClick={() => run.mutate({ intent: "protocol_question", question })}
            >
              {run.isPending && run.variables?.intent === "protocol_question" ? (
                <Loader2 size={13} className="animate-spin" aria-hidden="true" />
              ) : (
                <Search size={13} aria-hidden="true" />
              )}
              Ask
            </button>
          </div>
          <ul className="mt-1.5 flex flex-wrap gap-1">
            {SUGGESTED_QUESTIONS.map((suggestion) => (
              <li key={suggestion}>
                <button
                  type="button"
                  onClick={() => setQuestion(suggestion)}
                  className="rounded border border-line bg-base px-1.5 py-0.5 text-[10.5px] text-muted hover:border-info/40 hover:text-info"
                >
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-2 flex items-center gap-1.5 rounded border border-immediate/40 bg-immediate-dim p-2 text-[12px] text-immediate"
          >
            <CircleAlert size={13} aria-hidden="true" />
            {error}
          </p>
        ) : null}
      </section>

      {result ? <AgentResult result={result} /> : null}

      {/* History */}
      <section className="panel" aria-label="Agent run history">
        <div className="panel-head">
          <h2 className="panel-title">Recent runs</h2>
          <span className="text-[10px] text-faint">
            prompt hash · model · retrieved chunks · latency
          </span>
        </div>
        <div className="scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Agent</th>
                <th scope="col">By</th>
                <th scope="col">Mode</th>
                <th scope="col">Status</th>
                <th scope="col">Chunks</th>
                <th scope="col">Latency</th>
                <th scope="col">Prompt hash</th>
              </tr>
            </thead>
            <tbody>
              {(catalogue?.recent_runs ?? []).map((agentRun) => (
                <tr key={agentRun.id}>
                  <td className="whitespace-nowrap text-ink-2">{dateTime(agentRun.created_at)}</td>
                  <td className="text-ink">{agentRun.agent.replace(/_/g, " ")}</td>
                  <td className="text-ink-2">{agentRun.requested_by_name}</td>
                  <td>
                    <span
                      className={cn(
                        "chip",
                        agentRun.mode === "llm"
                          ? "border-ai/40 bg-ai-dim text-ai"
                          : "border-line bg-panel-2 text-muted",
                      )}
                    >
                      {agentRun.mode}
                    </span>
                  </td>
                  <td>
                    <span
                      className={cn(
                        "chip",
                        agentRun.status === "awaiting_human"
                          ? "border-ai/40 bg-ai-dim text-ai"
                          : "border-ok/35 bg-ok-dim text-ok",
                      )}
                    >
                      {agentRun.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="tabular-nums text-ink-2">
                    {agentRun.retrieved_chunk_ids?.length ?? 0}
                  </td>
                  <td className="tabular-nums text-faint">{agentRun.latency_ms} ms</td>
                  <td className="mono text-faint">
                    {agentRun.prompt_hash ? `${agentRun.prompt_hash.slice(0, 12)}…` : "—"}
                  </td>
                </tr>
              ))}
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-muted">
                    Loading…
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <p className="border-t border-line px-2.5 py-1.5 text-[10.5px] text-faint">
          The prompt itself is never stored — only its SHA-256, which is enough to prove which
          inputs produced an output without duplicating incident text.
        </p>
      </section>
    </div>
  );
}

function AgentResult({ result }: { result: AgentResultPayload }) {
  return (
    <section className="panel" aria-label="Agent output" aria-live="polite">
      <div className="panel-head flex-wrap">
        <div className="flex items-center gap-2">
          <Bot size={13} className="text-ai" aria-hidden="true" />
          <h2 className="panel-title">{result.agent.replace(/_/g, " ")}</h2>
          <AiBadge mode={result.mode} />
        </div>
        <span className="text-[10px] text-faint">confidence {pct(result.confidence)}</span>
      </div>

      <p className="flex items-start gap-1.5 border-b border-ai/25 bg-ai-dim px-3 py-1.5 text-[11px] text-ai">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        {result.banner}
      </p>

      <div className="space-y-3 p-3">
        <pre className="whitespace-pre-wrap break-words font-sans text-[12.5px] leading-relaxed text-ink-2">
          {result.summary}
        </pre>

        {result.uncertainty.length > 0 ? (
          <div className="rounded border border-priority/30 bg-priority-dim/40 p-2.5">
            <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-priority">
              <ShieldAlert size={12} aria-hidden="true" />
              What this does not know
            </h3>
            <ul className="space-y-0.5">
              {result.uncertainty.map((item) => (
                <li key={item} className="text-[12px] text-ink-2">
                  · {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {result.citations.length > 0 ? (
          <div>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-widest text-muted">
              Citations ({result.citations.length})
            </h3>
            <ul className="space-y-1">
              {result.citations.map((citation) => (
                <li key={citation.id} className="rounded border border-line bg-base p-2">
                  <p className="mono text-[10.5px] text-info">{citation.id}</p>
                  <p className="text-[11.5px] font-medium text-ink-2">{citation.title}</p>
                  {citation.preview ? (
                    <p className="mt-0.5 line-clamp-2 text-[11px] text-faint">{citation.preview}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
