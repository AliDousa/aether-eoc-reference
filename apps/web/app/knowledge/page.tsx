"use client";

/**
 * Knowledge corpus browser.
 *
 * Exists so a reviewer can check a citation by hand. An agent claims a
 * threshold; you open the cited section and read whether it says that. A
 * citation you cannot open is decoration, and this page is what stops the
 * citations elsewhere in the app from being decorative.
 */

import { useQuery } from "@tanstack/react-query";
import { BookOpen, FileWarning, Loader2, Search } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/format";

export default function KnowledgePage() {
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const { data: index, isLoading } = useQuery({ queryKey: ["knowledge"], queryFn: api.knowledge });

  const activeSource = selectedSource ?? index?.sources[0]?.source ?? null;

  const { data: document, isFetching } = useQuery({
    queryKey: ["knowledge", activeSource],
    queryFn: () => api.knowledgeSource(activeSource as string),
    enabled: Boolean(activeSource),
  });

  const filteredSections =
    query.trim().length > 0
      ? (index?.sources ?? []).flatMap((source) =>
          source.sections
            .filter((section) => section.title.toLowerCase().includes(query.toLowerCase()))
            .map((section) => ({ ...section, source: source.source })),
        )
      : [];

  return (
    <div className="flex flex-col gap-3">
      <section className="panel p-3">
        <h1 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
          <BookOpen size={15} aria-hidden="true" />
          Knowledge corpus
        </h1>
        <p className="mt-1 flex items-start gap-1.5 rounded border border-priority/35 bg-priority-dim p-2 text-[11.5px] text-priority">
          <FileWarning size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            {index?.notice ??
              "DEMO PROTOCOL — not official guidance. For software demonstration only."}{" "}
            These documents were written for this demonstration. They carry no clinical or
            operational authority and are not synchronised with any real guidance.
          </span>
        </p>
        <p className="mt-2 text-[11.5px] text-ink-2">
          {index?.sources.length ?? 0} documents · {index?.chunk_count ?? 0} retrievable sections.
          The protocol retriever answers only from these, and cites the section id it used.
        </p>
      </section>

      <div className="grid gap-3 lg:grid-cols-[16rem_1fr]">
        {/* Index */}
        <nav className="panel flex flex-col" aria-label="Knowledge documents">
          <div className="panel-head">
            <h2 className="panel-title">Documents</h2>
          </div>

          <div className="border-b border-line p-2">
            <div className="relative">
              <Search
                size={12}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-faint"
                aria-hidden="true"
              />
              <input
                className="field pl-6"
                placeholder="Find a section…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search section titles"
              />
            </div>
          </div>

          {query.trim() ? (
            <ul className="divide-y divide-line-soft overflow-y-auto">
              {filteredSections.map((section) => (
                <li key={section.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedSource(section.source);
                      setQuery("");
                    }}
                    className="w-full px-2.5 py-1.5 text-left hover:bg-panel-2"
                  >
                    <span className="block text-[12px] text-ink">{section.title}</span>
                    <span className="mono block text-[10px] text-faint">{section.source}</span>
                  </button>
                </li>
              ))}
              {filteredSections.length === 0 ? (
                <li className="px-2.5 py-3 text-center text-[11.5px] text-muted">No match.</li>
              ) : null}
            </ul>
          ) : (
            <ul className="divide-y divide-line-soft overflow-y-auto">
              {(index?.sources ?? []).map((source) => (
                <li key={source.source}>
                  <button
                    type="button"
                    onClick={() => setSelectedSource(source.source)}
                    aria-current={activeSource === source.source ? "true" : undefined}
                    className={cn(
                      "w-full px-2.5 py-2 text-left transition-colors",
                      activeSource === source.source
                        ? "bg-raised text-ink"
                        : "text-ink-2 hover:bg-panel-2",
                    )}
                  >
                    <span className="mono block break-all text-[11.5px]">{source.source}</span>
                    <span className="text-[10px] text-faint">{source.section_count} sections</span>
                  </button>
                </li>
              ))}
              {isLoading ? (
                <li className="px-2.5 py-3 text-center">
                  <Loader2
                    size={14}
                    className="mx-auto animate-spin text-muted"
                    aria-hidden="true"
                  />
                </li>
              ) : null}
            </ul>
          )}
        </nav>

        {/* Document */}
        <section className="panel min-w-0" aria-label="Document text">
          <div className="panel-head">
            <h2 className="panel-title mono">{activeSource ?? "—"}</h2>
            {isFetching ? (
              <Loader2 size={13} className="animate-spin text-muted" aria-hidden="true" />
            ) : null}
          </div>
          <div className="max-h-[calc(100vh-16rem)] overflow-y-auto p-3">
            {document ? (
              <pre className="whitespace-pre-wrap break-words font-sans text-[12.5px] leading-relaxed text-ink-2">
                {document.text}
              </pre>
            ) : (
              <p className="text-[12px] text-muted">Select a document.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
