/**
 * Status chips.
 *
 * Every chip renders an icon AND a text label, never a bare colour. The brief
 * for this repo requires it and so does WCAG 2.2, but the operational reason is
 * simpler: a red dot means nothing to someone who cannot distinguish it from
 * the amber one, and "IMMEDIATE" means the same thing to everybody.
 */

import {
  AlertTriangle,
  Ban,
  Bot,
  CheckCircle2,
  CircleDashed,
  CircleDot,
  Clock,
  FileEdit,
  PackageCheck,
  Send,
  ShieldAlert,
  Truck,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/format";
import type { Priority, RecommendationStatus, RequestState } from "@/lib/types";

interface ChipStyle {
  label: string;
  Icon: LucideIcon;
  className: string;
}

const PRIORITY_STYLES: Record<Priority, ChipStyle> = {
  immediate: {
    label: "IMMEDIATE",
    Icon: AlertTriangle,
    className: "text-immediate bg-immediate-dim border-immediate/40",
  },
  priority: {
    label: "PRIORITY",
    Icon: CircleDot,
    className: "text-priority bg-priority-dim border-priority/40",
  },
  routine: {
    label: "ROUTINE",
    Icon: CircleDashed,
    className: "text-routine bg-routine-dim border-routine/30",
  },
};

const STATE_STYLES: Record<RequestState, ChipStyle> = {
  draft: { label: "Draft", Icon: FileEdit, className: "text-faint bg-routine-dim border-line" },
  submitted: { label: "Submitted", Icon: Send, className: "text-info bg-info-dim border-info/35" },
  recommended: {
    label: "Awaiting decision",
    Icon: Bot,
    className: "text-ai bg-ai-dim border-ai/40",
  },
  approved: {
    label: "Approved",
    Icon: CheckCircle2,
    className: "text-ok bg-ok-dim border-ok/35",
  },
  modified: {
    label: "Modified + approved",
    Icon: FileEdit,
    className: "text-ok bg-ok-dim border-ok/35",
  },
  rejected: {
    label: "Rejected",
    Icon: XCircle,
    className: "text-immediate bg-immediate-dim border-immediate/40",
  },
  tasked: { label: "Tasked", Icon: Truck, className: "text-info bg-info-dim border-info/35" },
  fulfilled: {
    label: "Fulfilled",
    Icon: PackageCheck,
    className: "text-ok bg-ok-dim border-ok/35",
  },
  cancelled: { label: "Cancelled", Icon: Ban, className: "text-faint bg-routine-dim border-line" },
};

const RECOMMENDATION_STYLES: Record<RecommendationStatus, ChipStyle> = {
  pending: {
    label: "Awaiting human",
    Icon: Clock,
    className: "text-ai bg-ai-dim border-ai/40",
  },
  approved: {
    label: "Approved by human",
    Icon: CheckCircle2,
    className: "text-ok bg-ok-dim border-ok/35",
  },
  modified: {
    label: "Modified by human",
    Icon: FileEdit,
    className: "text-ok bg-ok-dim border-ok/35",
  },
  rejected: {
    label: "Rejected by human",
    Icon: XCircle,
    className: "text-immediate bg-immediate-dim border-immediate/40",
  },
};

function Chip({ label, Icon, className, title }: ChipStyle & { title?: string }) {
  return (
    <span className={cn("chip", className)} title={title}>
      <Icon size={11} aria-hidden="true" strokeWidth={2.25} />
      {label}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  const style = PRIORITY_STYLES[priority];
  return <Chip {...style} title={`Priority: ${style.label}`} />;
}

export function StateBadge({ state }: { state: RequestState }) {
  const style = STATE_STYLES[state];
  return <Chip {...style} title={`State: ${state}`} />;
}

export function RecommendationBadge({ status }: { status: RecommendationStatus }) {
  const style = RECOMMENDATION_STYLES[status];
  return <Chip {...style} title={`Recommendation: ${status}`} />;
}

/** Marks anything produced by an agent. Never used on human-authored content. */
export function AiBadge({ mode }: { mode?: string }) {
  return (
    <Chip
      label={mode === "llm" ? "AI · model" : "AI · rules"}
      Icon={Bot}
      className="text-ai bg-ai-dim border-ai/40"
      title={
        mode === "llm"
          ? "Generated with a language model"
          : "Generated deterministically from rules — no model configured"
      }
    />
  );
}

export function EquityBadge({ passed }: { passed: boolean }) {
  return passed ? (
    <Chip
      label="Equity floor OK"
      Icon={CheckCircle2}
      className="text-ok bg-ok-dim border-ok/35"
      title="No high-need site is reduced to zero by this allocation."
    />
  ) : (
    <Chip
      label="Equity floor breached"
      Icon={ShieldAlert}
      className="text-immediate bg-immediate-dim border-immediate/40"
      title="This allocation would zero out a high-need site."
    />
  );
}

export function ShortfallBadge({ shortfall, unit }: { shortfall: number; unit: string }) {
  if (shortfall <= 0) {
    return (
      <Chip
        label="Fully filled"
        Icon={CheckCircle2}
        className="text-ok bg-ok-dim border-ok/35"
        title="The request can be filled in full."
      />
    );
  }
  return (
    <Chip
      label={`Short ${shortfall} ${unit}`}
      Icon={AlertTriangle}
      className="text-priority bg-priority-dim border-priority/40"
      title="The request cannot be filled in full from available stock."
    />
  );
}
