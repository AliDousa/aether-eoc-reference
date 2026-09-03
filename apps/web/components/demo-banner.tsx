import { FlaskConical } from "lucide-react";

/**
 * Shown on every page, above everything else.
 *
 * Not dismissible and not subtle. A screenshot of this tool taken out of
 * context should still say, unambiguously, that it is not a live EOC.
 */
export function DemoBanner() {
  return (
    <div
      role="note"
      aria-label="Synthetic demonstration notice"
      className="flex items-center justify-center gap-2 border-b border-priority/30 bg-priority-dim px-3 py-1 text-center text-[11px] font-semibold tracking-wide text-priority"
    >
      <FlaskConical size={12} aria-hidden="true" />
      <span>SYNTHETIC DEMO — not a live EOC. All data is fictional.</span>
    </div>
  );
}
