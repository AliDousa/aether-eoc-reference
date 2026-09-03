"""Resource requests, recommendations, and human decisions.

The decision endpoint at the bottom is the one worth reading: it is the only
route in the application from an agent proposal to a stock movement, and it
goes through a human.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import board, decisions
from app import requests as requests_service
from app.agents import supervisor
from app.deps import CorrelationDep, CurrentUserDep, DbSession
from app.enums import RequestState
from app.errors import NotFound
from app.models import Recommendation
from app.schemas import CreateRequestBody, DecisionBody, TransitionRequestBody
from app.security import Permission, require

router = APIRouter(prefix="/api", tags=["requests"])


@router.get("/requests")
async def list_requests(session: DbSession, incident_id: str | None = None) -> dict[str, Any]:
    if incident_id is None:
        incident = await board.current_incident(session)
        if incident is None:
            raise NotFound("No incident has been seeded. Run `make seed`.")
        incident_id = incident.id

    requests = await requests_service.list_for_incident(session, incident_id)
    payload = []
    for request in requests:
        recommendation = await requests_service.latest_recommendation(session, request.id)
        payload.append(requests_service.serialize(request, recommendation=recommendation))
    return {"requests": payload}


@router.get("/requests/{request_id}")
async def get_request(request_id: str, session: DbSession) -> dict[str, Any]:
    request = await requests_service.get_or_404(session, request_id)
    recommendation = await requests_service.latest_recommendation(session, request.id)
    payload = requests_service.serialize(request, recommendation=recommendation)

    # The state-change history for this request, straight from the audit log,
    # so the detail timeline is the audit trail rather than a parallel story.
    from sqlalchemy import select

    from app.clock import iso
    from app.models import AuditEvent

    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.entity_id == request_id,
            AuditEvent.entity_type == "resource_request",
        )
        .order_by(AuditEvent.seq.asc())
    )
    history = list((await session.execute(stmt)).scalars())
    payload["timeline"] = [
        {
            "seq": event.seq,
            "at": iso(event.at),
            "action": event.action,
            "actor": event.actor_label,
            "correlation_id": event.correlation_id,
            "ai_trace_id": event.ai_trace_id,
        }
        for event in history
    ]
    return payload


@router.post("/requests", status_code=201)
async def create_request(
    body: CreateRequestBody,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    require(user, Permission.CREATE_REQUEST)
    incident = await board.current_incident(session)
    if incident is None:
        raise NotFound("No incident has been seeded. Run `make seed`.")

    request = await requests_service.create(
        session,
        incident_id=incident.id,
        sku_id=body.sku_id,
        quantity=body.quantity,
        priority=body.priority,
        requesting_section=body.requesting_section,
        justification=body.justification,
        destination_site_id=body.destination_site_id,
        actor=user,
        correlation_id=correlation_id,
    )
    await session.commit()
    await session.refresh(request)
    return {"request": requests_service.serialize(request)}


@router.post("/requests/{request_id}/transition")
async def transition_request(
    request_id: str,
    body: TransitionRequestBody,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    """Move a request along the lifecycle.

    Illegal moves raise 409 with the permitted set, so a client never has to
    guess what is allowed next.
    """
    require(user, Permission.SUBMIT_REQUEST)
    request = await requests_service.get_or_404(session, request_id)

    # Committing states are reached only through a recommendation decision, so
    # that inventory never moves without one.
    if RequestState(body.target) in {RequestState.APPROVED, RequestState.MODIFIED}:
        require(user, Permission.DECIDE_LOGISTICS)

    await requests_service.transition(
        session,
        request,
        RequestState(body.target),
        actor=user,
        correlation_id=correlation_id,
        note=body.note,
    )
    await session.commit()
    await session.refresh(request)
    return {"request": requests_service.serialize(request)}


@router.post("/requests/{request_id}/recommend")
async def recommend(
    request_id: str,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    """Ask the Resource Recommender for an allocation.

    Produces a proposal and moves the request to ``recommended``. Deliberately
    changes no stock — see the ``inventory`` block in the response, which is
    the board's own view and is unchanged by this call.
    """
    require(user, Permission.RUN_AGENT)
    request = await requests_service.get_or_404(session, request_id)

    run, result, recommendation = await supervisor.run_intent(
        session,
        incident_id=request.incident_id,
        intent="resource_recommendation",
        actor=user,
        correlation_id=correlation_id,
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(request)

    return {
        "request": requests_service.serialize(request, recommendation=recommendation),
        "agent_run": supervisor.serialize_run(run),
        "result": result.as_payload(),
    }


@router.post("/recommendations/{recommendation_id}/decide")
async def decide(
    recommendation_id: str,
    body: DecisionBody,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    """Accept, edit, or refuse a recommendation. The human-in-the-loop gate.

    Authority is checked in ``app.decisions``; the equity floor is re-evaluated
    against live stock there too, so an edited plan cannot bypass it.
    """
    recommendation = await session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise NotFound(f"Unknown recommendation '{recommendation_id}'.")

    if body.decision == "reject":
        outcome = await decisions.reject(
            session,
            recommendation,
            actor=user,
            correlation_id=correlation_id,
            reason=body.reason,
        )
    else:
        modified_legs = (
            [leg.model_dump() for leg in body.modified_legs]
            if body.decision == "modify" and body.modified_legs is not None
            else None
        )
        outcome = await decisions.approve(
            session,
            recommendation,
            actor=user,
            correlation_id=correlation_id,
            modified_legs=modified_legs,
            reason=body.reason,
            override_equity=body.override_equity,
        )

    await session.commit()
    await session.refresh(outcome.request)
    await session.refresh(outcome.recommendation)

    return {
        "request": requests_service.serialize(
            outcome.request, recommendation=outcome.recommendation
        ),
        "moved_total": outcome.moved_total,
        "audit": {
            "decision_event_id": outcome.decision_audit_event.id,
            "inventory_event_ids": [e.id for e in outcome.inventory_audit_events],
        },
        "inventory": await board.inventory_rows(session),
    }
