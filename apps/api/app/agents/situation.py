"""Situation Assessment agent.

Summarises the incident and the recent activity stream in the shape of
``knowledge/ics-sitrep-template.md``. Advisory only: nothing it produces can
move a resource, so it completes without a human gate.

Two properties are non-negotiable and are enforced in the deterministic path
rather than requested in a prompt:

* **Every claim is cited.** Citations point at activity-event ids and at
  knowledge chunks that exist on disk.
* **Uncertainty is never empty.** Section 6 of the SITREP template makes the
  information-gaps section mandatory, and an assessment that admits nothing is
  the failure mode this whole repo argues against.

When a model is configured it writes the prose in section 2 only; the
structured facts, citations, and gaps are computed either way, so a model
outage changes the tone of one paragraph and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import rag
from app.agents import llm
from app.agents.base import AgentResult
from app.agents.redact import RedactionMap
from app.enums import AgentName, AgentRunStatus

_SYSTEM_PROMPT = (
    "You are a Planning Section duty officer in a public-health Emergency "
    "Operations Center. Write the 'Current situation' paragraph of a SITREP: "
    "two to four sentences, plain language, present tense. State what changed, "
    "what is trending worse, and what is trending better. Do not invent facts "
    "beyond the supplied events. Do not give clinical advice. Names have "
    "already been replaced with role tokens; keep them as tokens."
)


@dataclass
class SituationInput:
    """Everything the agent is allowed to see. Assembled by the supervisor."""

    incident_name: str
    incident_type: str
    severity: str
    status: str
    period: str
    activated_at: str
    objectives: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    open_requests: list[dict[str, Any]] = field(default_factory=list)
    unfilled_immediate: int = 0
    sites_below_reorder: list[dict[str, Any]] = field(default_factory=list)
    pending_reviews: int = 0


def _deterministic_paragraph(data: SituationInput) -> str:
    """Rule-derived 'current situation' text used when no model is configured."""
    parts: list[str] = [
        f"{data.incident_name} remains {data.status} at severity {data.severity} "
        f"in operational period {data.period}."
    ]

    if data.events:
        recent_kinds = [e.get("kind", "") for e in data.events[:8]]
        movement = sum(1 for k in recent_kinds if k == "resource_movement")
        requests = sum(1 for k in recent_kinds if k == "resource_request")
        parts.append(
            f"The last {len(data.events)} log entries show {requests} resource request(s) "
            f"and {movement} stock movement(s)."
        )

    if data.unfilled_immediate:
        parts.append(
            f"{data.unfilled_immediate} IMMEDIATE request(s) remain unfilled — this is the "
            "limiting factor for the next operational period."
        )
    else:
        parts.append("No IMMEDIATE request is currently unfilled.")

    if data.sites_below_reorder:
        names = ", ".join(s["site_name"] for s in data.sites_below_reorder[:3])
        parts.append(f"Sites below reorder point: {names}.")
    else:
        parts.append("No site is below its reorder point.")

    return " ".join(parts)


def _build_sections(data: SituationInput, paragraph: str) -> list[dict[str, str]]:
    """SITREP sections in template order."""
    resource_lines: list[str] = []
    if data.open_requests:
        for request in data.open_requests[:5]:
            resource_lines.append(
                f"{request['priority'].upper()}: {request['quantity']} x {request['sku_name']} "
                f"-> {request.get('destination') or 'unassigned'} ({request['state']})"
            )
    else:
        resource_lines.append("No open resource requests.")
    if data.sites_below_reorder:
        for site in data.sites_below_reorder:
            resource_lines.append(
                f"Below reorder: {site['site_name']} — {site['sku_name']} "
                f"{site['available']}/{site['reorder_point']}"
            )

    objectives = data.objectives or ["No objectives recorded."]

    return [
        {"title": "2. Current situation", "body": paragraph},
        {
            "title": "3. Incident objectives",
            "body": "\n".join(f"- {objective}" for objective in objectives),
        },
        {"title": "4. Resource status", "body": "\n".join(f"- {line}" for line in resource_lines)},
        {
            "title": "5. Pending decisions",
            "body": (
                f"- {data.pending_reviews} AI recommendation(s) awaiting human decision."
                if data.pending_reviews
                else "- No recommendations awaiting decision."
            ),
        },
    ]


def _gaps(data: SituationInput) -> list[str]:
    """Section 6. Never returns an empty list."""
    gaps: list[str] = []
    if data.unfilled_immediate:
        gaps.append("Resupply timing for unfilled IMMEDIATE requests is not known to this system.")
    if data.sites_below_reorder:
        gaps.append("Physical stock counts are unverified; figures are as recorded on the board.")
    if data.pending_reviews:
        gaps.append(
            f"{data.pending_reviews} recommendation(s) are unreviewed, so the resource picture "
            "may change once decisions are made."
        )
    gaps.append(
        "Occupancy and clinical figures are only as current as the last 30-minute site report."
    )
    gaps.append(
        "This assessment covers the seeded activity stream only. It has no external feeds, "
        "no surveillance data, and no weather service."
    )
    return gaps


async def run(data: SituationInput, *, mapping: RedactionMap | None = None) -> AgentResult:
    paragraph = _deterministic_paragraph(data)
    mode = "fixture"
    model_id = "deterministic-rules-v1"
    prompt_hash = ""

    if llm.is_enabled():
        event_lines = "\n".join(
            f"- [{e['id']}] {e.get('created_at', '')} {e.get('kind', '')}: {e.get('body', '')}"
            for e in data.events[:20]
        )
        user_prompt = (
            f"Incident: {data.incident_name} ({data.incident_type}), severity {data.severity}, "
            f"status {data.status}, period {data.period}.\n"
            f"Unfilled IMMEDIATE requests: {data.unfilled_immediate}.\n"
            f"Sites below reorder: {len(data.sites_below_reorder)}.\n"
            f"Recent activity:\n{event_lines}\n"
        )
        prompt_hash = llm.prompt_hash(user_prompt)
        result = await llm.complete(system=_SYSTEM_PROMPT, user=user_prompt, mapping=mapping)
        if result.ok:
            paragraph = result.text
            mode = "llm"
            model_id = result.model_id
        # On failure the deterministic paragraph already computed stands.

    sections = _build_sections(data, paragraph)

    # Citations are the evidence for the assessment: the activity events it read,
    # plus the template section that defines the shape.
    citations: list[dict[str, Any]] = [
        {
            "id": event["id"],
            "source": "activity_stream",
            "title": f"{event.get('kind', 'event')} @ {event.get('created_at', '')}",
            "anchor": event["id"],
            "preview": str(event.get("body", ""))[:280],
            "score": 0.0,
        }
        for event in data.events[:6]
    ]
    for hit in rag.search("situation report information gaps uncertainty resource status", limit=2):
        citations.append(hit.as_citation())

    summary = "\n\n".join(f"{section['title']}\n{section['body']}" for section in sections)

    return AgentResult(
        agent=AgentName.SITUATION_ASSESSMENT,
        intent="situation_summary",
        summary=summary,
        structured={
            "incident": data.incident_name,
            "period": data.period,
            "sections": sections,
            "unfilled_immediate": data.unfilled_immediate,
            "sites_below_reorder": data.sites_below_reorder,
            "pending_reviews": data.pending_reviews,
            "events_considered": [e["id"] for e in data.events[:20]],
        },
        citations=citations,
        # Deliberately not high. This is a summary of a partial picture, and
        # presenting it as near-certain would be the wrong lesson.
        confidence=0.7 if mode == "fixture" else 0.74,
        uncertainty=_gaps(data),
        mode=mode,
        model_id=model_id,
        prompt_hash=prompt_hash,
        raw_output=summary,
        requires_human=False,
        status=AgentRunStatus.COMPLETE,
    )
