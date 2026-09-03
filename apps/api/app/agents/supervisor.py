"""Agent supervisor.

An explicit router, not a framework. Roughly two hundred lines of dispatch,
input assembly, and persistence — which is the whole orchestration story and is
readable in one sitting (ADR-0005).

Responsibilities, all of which are deliberately *not* delegated to the
specialists:

* Route an intent to exactly one specialist. Specialists never call each other.
* Assemble the inputs a specialist is allowed to see, from the database.
* Build the redaction map so display names never reach a model.
* Persist the run: mode, model id, prompt hash, retrieved chunk ids, raw and
  structured output, latency, correlation id.
* Decide whether the output may act. Anything that would move resources is
  written as ``AWAITING_HUMAN`` and materialised as a ``Recommendation`` in
  ``pending`` — the agent path has no route to ``app.inventory`` at all.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import activity, audit, rag
from app.agents import protocol, recommender, situation
from app.agents.base import AgentResult
from app.agents.recommender import Candidate
from app.agents.redact import RedactionMap, build_map
from app.clock import iso, now
from app.enums import (
    ActivityKind,
    AgentName,
    IcsRole,
    Priority,
    RecommendationStatus,
    RequestState,
)
from app.errors import DomainError, NotFound
from app.ids import new_id
from app.models import (
    AgentRun,
    Incident,
    InventoryPosition,
    Operator,
    Recommendation,
    ResourceRequest,
)
from app.realtime import safe_broadcast
from app.security import CurrentUser

# The only intents this supervisor will route. An unknown intent is refused
# rather than guessed at.
INTENTS: dict[str, AgentName] = {
    "situation_summary": AgentName.SITUATION_ASSESSMENT,
    "protocol_question": AgentName.PROTOCOL_RETRIEVER,
    "resource_recommendation": AgentName.RESOURCE_RECOMMENDER,
}


class UnknownIntent(DomainError):
    status_code = 400
    code = "unknown_intent"


async def _redaction_map(session: AsyncSession) -> RedactionMap:
    """Map every operator display name to a role token before any model call."""
    operators = list((await session.execute(select(Operator))).scalars())
    return build_map([(op.display_name, IcsRole(op.ics_role)) for op in operators])


async def _situation_input(session: AsyncSession, incident: Incident) -> situation.SituationInput:
    from app import requests as requests_service

    events = await activity.recent(session, incident.id, limit=20)
    open_requests = await requests_service.list_for_incident(
        session,
        incident.id,
        states={
            RequestState.SUBMITTED,
            RequestState.RECOMMENDED,
            RequestState.APPROVED,
            RequestState.MODIFIED,
            RequestState.TASKED,
        },
    )

    positions = list((await session.execute(select(InventoryPosition))).scalars())
    below = [
        {
            "site_name": position.site.name,
            "sku_name": position.sku.name,
            "available": position.available,
            "reorder_point": position.reorder_point,
        }
        for position in positions
        if position.below_reorder
    ]

    pending = (
        await session.execute(
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.status == RecommendationStatus.PENDING.value)
        )
    ).scalar_one()

    unfilled_immediate = sum(
        1
        for request in open_requests
        if Priority(request.priority) is Priority.IMMEDIATE
        and RequestState(request.state) in {RequestState.SUBMITTED, RequestState.RECOMMENDED}
    )

    return situation.SituationInput(
        incident_name=incident.name,
        incident_type=incident.type,
        severity=str(incident.severity),
        status=str(incident.status),
        period=incident.current_period,
        activated_at=iso(incident.activated_at),
        objectives=list(incident.objectives or []),
        events=[
            {
                "id": event.id,
                "kind": str(event.kind),
                "body": event.body,
                "created_at": iso(event.created_at),
                "actor_name": event.actor.display_name if event.actor else "SYSTEM",
            }
            for event in events
        ],
        open_requests=[
            {
                "id": request.id,
                "priority": str(request.priority),
                "quantity": request.quantity,
                "sku_name": request.sku.name,
                "state": str(request.state),
                "destination": (
                    request.destination_site.name if request.destination_site else None
                ),
            }
            for request in open_requests
        ],
        unfilled_immediate=unfilled_immediate,
        sites_below_reorder=below,
        pending_reviews=int(pending),
    )


async def _candidates_for(session: AsyncSession, request: ResourceRequest) -> list[Candidate]:
    """Source sites for a request's SKU, excluding the destination itself."""
    stmt = select(InventoryPosition).where(InventoryPosition.sku_id == request.sku_id)
    positions = list((await session.execute(stmt)).scalars())
    return [
        Candidate(
            site_id=position.site_id,
            site_name=position.site.name,
            equity_priority=position.site.equity_priority,
            available=position.available,
            reorder_point=position.reorder_point,
        )
        for position in positions
        if position.site_id != request.destination_site_id
    ]


async def _persist(
    session: AsyncSession,
    *,
    incident: Incident,
    result: AgentResult,
    actor: CurrentUser,
    correlation_id: str,
    latency_ms: int,
) -> AgentRun:
    run = AgentRun(
        id=new_id("run"),
        incident_id=incident.id,
        agent=result.agent,
        intent=result.intent,
        requested_by=actor.id,
        mode=result.mode,
        model_id=result.model_id,
        prompt_hash=result.prompt_hash,
        retrieved_chunk_ids=result.citation_ids,
        raw_output=result.raw_output,
        structured_output=result.as_payload(),
        status=result.status,
        latency_ms=latency_ms,
        correlation_id=correlation_id,
        created_at=now(),
    )
    session.add(run)
    await session.flush()
    # A freshly added instance has never been SELECTed, so its `selectin`
    # relationships are unloaded. Serialising it later would try to lazy-load
    # `requester` from sync context and raise MissingGreenlet. Refreshing here
    # applies the configured eager loaders once, at the point of creation.
    await session.refresh(run)

    await audit.record(
        session,
        action=f"ai.{result.intent}",
        entity_type="agent_run",
        entity_id=run.id,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        after={
            "agent": result.agent.value,
            "mode": result.mode,
            "model_id": result.model_id,
            "status": result.status.value,
            "confidence": round(result.confidence, 3),
            "citations": result.citation_ids,
            "requires_human": result.requires_human,
            "prompt_hash": result.prompt_hash,
        },
        ai_trace_id=run.id,
    )
    return run


async def run_intent(
    session: AsyncSession,
    *,
    incident_id: str,
    intent: str,
    actor: CurrentUser,
    correlation_id: str,
    question: str | None = None,
    request_id: str | None = None,
) -> tuple[AgentRun, AgentResult, Recommendation | None]:
    """Route one intent, persist the trace, and return what happened."""
    if intent not in INTENTS:
        raise UnknownIntent(f"Unknown intent '{intent}'.", detail={"supported": sorted(INTENTS)})

    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise NotFound(f"Unknown incident '{incident_id}'.")

    mapping = await _redaction_map(session)
    started = time.perf_counter()
    recommendation: Recommendation | None = None
    request: ResourceRequest | None = None

    if intent == "situation_summary":
        result = await situation.run(await _situation_input(session, incident), mapping=mapping)

    elif intent == "protocol_question":
        if not (question or "").strip():
            raise UnknownIntent("A protocol question requires question text.")
        result = await protocol.run(question or "", mapping=mapping)

    else:  # resource_recommendation
        if not request_id:
            raise UnknownIntent("A resource recommendation requires request_id.")
        request = await session.get(ResourceRequest, request_id)
        if request is None:
            raise NotFound(f"Unknown resource request '{request_id}'.")
        result = await recommender.run(
            sku_code=request.sku.code,
            sku_name=request.sku.name,
            requested=request.quantity,
            priority=Priority(request.priority),
            candidates=await _candidates_for(session, request),
            destination_site_id=request.destination_site_id,
            destination_site_name=(
                request.destination_site.name if request.destination_site else None
            ),
            destination_equity=(
                request.destination_site.equity_priority if request.destination_site else None
            ),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    run = await _persist(
        session,
        incident=incident,
        result=result,
        actor=actor,
        correlation_id=correlation_id,
        latency_ms=latency_ms,
    )

    # Output that could move resources is materialised as a pending
    # recommendation. This is the human-in-the-loop gate: the request advances
    # to `recommended`, and nothing else happens until someone decides.
    if result.requires_human and request is not None:
        from app import requests as requests_service

        recommendation = Recommendation(
            id=new_id("rec"),
            request_id=request.id,
            agent=result.agent,
            agent_run_id=run.id,
            payload_json=result.structured,
            equity_review_json=result.structured.get("equity_review", {}),
            citations=result.citation_ids,
            confidence=result.confidence,
            rationale=result.summary,
            status=RecommendationStatus.PENDING,
            created_at=now(),
        )
        session.add(recommendation)
        await session.flush()
        await session.refresh(recommendation)  # load relationships before serialising

        if RequestState(request.state) is RequestState.SUBMITTED:
            await requests_service.transition(
                session,
                request,
                RequestState.RECOMMENDED,
                actor=actor,
                correlation_id=correlation_id,
                note="Recommendation generated; awaiting human decision.",
                ai_trace_id=run.id,
            )

    await activity.add(
        session,
        incident_id=incident.id,
        kind=ActivityKind.AGENT_OUTPUT,
        body=(
            f"{result.agent.value.replace('_', ' ').title()} ran for "
            f"{actor.display_name} ({result.mode} mode)."
            + (" Awaiting human decision." if result.requires_human else "")
        ),
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        meta={
            "agent_run_id": run.id,
            "agent": result.agent.value,
            "status": result.status.value,
            "citations": result.citation_ids,
        },
        ai_trace_id=run.id,
    )

    await safe_broadcast(
        incident.id,
        "agent.completed",
        {
            "agent_run_id": run.id,
            "agent": result.agent.value,
            "status": result.status.value,
            "request_id": request.id if request else None,
        },
    )

    return run, result, recommendation


def serialize_run(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "incident_id": run.incident_id,
        "agent": str(run.agent),
        "intent": run.intent,
        "requested_by": run.requested_by,
        "requested_by_name": run.requester.display_name if run.requester else "SYSTEM",
        "mode": run.mode,
        "model_id": run.model_id,
        "prompt_hash": run.prompt_hash,
        "retrieved_chunk_ids": run.retrieved_chunk_ids or [],
        "structured_output": run.structured_output or {},
        "raw_output": run.raw_output,
        "status": str(run.status),
        "latency_ms": run.latency_ms,
        "correlation_id": run.correlation_id,
        "created_at": iso(run.created_at),
    }


def available_sources() -> list[str]:
    """Knowledge files the retriever can cite. Surfaced on the Agents page."""
    return rag.get_corpus().sources
