"""Shared agent result type.

Specialists are plain async functions returning an :class:`AgentResult`. They
do not touch the database, do not call each other, and do not decide whether
their output is allowed to act — the supervisor does all three. Keeping the
specialists side-effect free is what makes them testable without a session and
what makes "the AI cannot move stock" a structural property rather than a
promise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.enums import AgentName, AgentRunStatus

# Shown verbatim above every agent answer in the UI.
VERIFY_BANNER = "AI-suggested — verify with current official guidance."


@dataclass
class AgentResult:
    """One specialist's output, before the supervisor persists it."""

    agent: AgentName
    intent: str
    # Human-readable answer rendered in the UI.
    summary: str
    # Machine-readable payload; shape is documented per agent in docs/AI_SPEC.md.
    structured: dict[str, Any] = field(default_factory=dict)
    # Citations as returned by rag.Hit.as_citation(); every id resolves on disk.
    citations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    # Explicit statements of what the agent does not know. Never empty for the
    # situation agent: an assessment with no stated uncertainty is a red flag,
    # per knowledge/ics-sitrep-template.md section 6.
    uncertainty: list[str] = field(default_factory=list)
    mode: str = "fixture"  # "fixture" | "llm"
    model_id: str = "deterministic-rules-v1"
    prompt_hash: str = ""
    raw_output: str = ""
    # True when acting on this output would move resources, change public
    # comms, or set policy. The supervisor turns this into AWAITING_HUMAN.
    requires_human: bool = False
    status: AgentRunStatus = AgentRunStatus.COMPLETE

    @property
    def citation_ids(self) -> list[str]:
        return [str(c["id"]) for c in self.citations]

    def as_payload(self) -> dict[str, Any]:
        return {
            "agent": self.agent.value,
            "intent": self.intent,
            "summary": self.summary,
            "structured": self.structured,
            "citations": self.citations,
            "confidence": round(self.confidence, 3),
            "uncertainty": self.uncertainty,
            "mode": self.mode,
            "model_id": self.model_id,
            "requires_human": self.requires_human,
            "banner": VERIFY_BANNER,
        }
