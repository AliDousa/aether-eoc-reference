"""Resource-request lifecycle service.

Every state change goes through :func:`transition`, which validates the move
against ``app.state_machine``, writes an audit row, appends to the activity
stream, and pushes the board update. Handlers never mutate ``state`` directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import activity, audit
from app.clock import iso, now
from app.enums import ActivityKind, IcsSection, Priority, RequestState
from app.errors import NotFound
from app.ids import new_id
from app.models import Recommendation, ResourceRequest
from app.realtime import safe_broadcast
from app.security import CurrentUser
from app.state_machine import allowed_transitions, assert_transition

# Terminal-ish states that the board treats as "no longer awaiting action".
CLOSED_STATES = {RequestState.FULFILLED, RequestState.REJECTED, RequestState.CANCELLED}


def serialize(
    request: ResourceRequest, *, recommendation: Recommendation | None = None
) -> dict[str, Any]:
    """API shape for a request. Includes the next legal moves.

    Returning ``allowed_transitions`` means the UI renders the real options
    from the server's rules instead of duplicating the state machine in
    TypeScript and drifting out of sync.
    """
    state = RequestState(request.state)
    payload: dict[str, Any] = {
        "id": request.id,
        "incident_id": request.incident_id,
        "sku": {
            "id": request.sku.id,
            "code": request.sku.code,
            "name": request.sku.name,
            "unit": request.sku.unit,
            "category": request.sku.category,
        },
        "quantity": request.quantity,
        "priority": request.priority.value
        if isinstance(request.priority, Priority)
        else request.priority,
        "requesting_section": request.requesting_section.value
        if isinstance(request.requesting_section, IcsSection)
        else request.requesting_section,
        "destination_site": (
            {
                "id": request.destination_site.id,
                "name": request.destination_site.name,
                "kind": request.destination_site.kind.value,
                "equity_priority": request.destination_site.equity_priority,
            }
            if request.destination_site
            else None
        ),
        "justification": request.justification,
        "state": state.value,
        "allowed_transitions": sorted(s.value for s in allowed_transitions(state)),
        "is_open": state not in CLOSED_STATES,
        "created_by": request.created_by,
        "created_by_name": request.creator.display_name if request.creator else "SYSTEM",
        "created_at": iso(request.created_at),
        "updated_at": iso(request.updated_at),
    }
    if recommendation is not None:
        payload["recommendation"] = serialize_recommendation(recommendation)
    return payload


def serialize_recommendation(rec: Recommendation) -> dict[str, Any]:
    return {
        "id": rec.id,
        "request_id": rec.request_id,
        "agent": rec.agent.value if hasattr(rec.agent, "value") else str(rec.agent),
        "agent_run_id": rec.agent_run_id,
        "payload": rec.payload_json or {},
        "equity_review": rec.equity_review_json or {},
        "citations": rec.citations or [],
        "confidence": rec.confidence,
        "rationale": rec.rationale,
        "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
        "decided_by": rec.decided_by,
        "decided_by_name": rec.decider.display_name if rec.decider else None,
        "decided_at": iso(rec.decided_at) if rec.decided_at else None,
        "decision_reason": rec.decision_reason,
        "decided_payload": rec.decided_payload_json or {},
        "created_at": iso(rec.created_at),
    }


async def get_or_404(session: AsyncSession, request_id: str) -> ResourceRequest:
    request = await session.get(ResourceRequest, request_id)
    if request is None:
        raise NotFound(f"Unknown resource request '{request_id}'.")
    return request


async def latest_recommendation(session: AsyncSession, request_id: str) -> Recommendation | None:
    stmt = (
        select(Recommendation)
        .where(Recommendation.request_id == request_id)
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_incident(
    session: AsyncSession, incident_id: str, *, states: set[RequestState] | None = None
) -> list[ResourceRequest]:
    stmt = select(ResourceRequest).where(ResourceRequest.incident_id == incident_id)
    if states:
        stmt = stmt.where(ResourceRequest.state.in_([s.value for s in states]))
    # Most urgent first, then newest: the order a Logistics chief works the queue.
    stmt = stmt.order_by(ResourceRequest.created_at.desc())
    rows = list((await session.execute(stmt)).scalars())
    return sorted(rows, key=lambda r: (-Priority(r.priority).rank, r.created_at), reverse=False)


async def create(
    session: AsyncSession,
    *,
    incident_id: str,
    sku_id: str,
    quantity: int,
    priority: Priority,
    requesting_section: IcsSection,
    justification: str,
    destination_site_id: str | None,
    actor: CurrentUser,
    correlation_id: str,
    initial_state: RequestState = RequestState.SUBMITTED,
) -> ResourceRequest:
    """Create a request and log it.

    Defaults to ``SUBMITTED`` rather than ``DRAFT``: the demo's create form is
    a submission, and leaving drafts lying around would add a state with no
    screen behind it.
    """
    request = ResourceRequest(
        id=new_id("req"),
        incident_id=incident_id,
        sku_id=sku_id,
        quantity=quantity,
        priority=priority,
        requesting_section=requesting_section,
        destination_site_id=destination_site_id,
        justification=justification,
        state=initial_state,
        created_by=actor.id,
        created_at=now(),
        updated_at=now(),
    )
    session.add(request)
    await session.flush()
    await session.refresh(request)

    await audit.record(
        session,
        action="request.created",
        entity_type="resource_request",
        entity_id=request.id,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        after=audit.snapshot(request),
    )

    await activity.add(
        session,
        incident_id=incident_id,
        kind=ActivityKind.RESOURCE_REQUEST,
        body=(
            f"{actor.display_name} raised a {priority.value.upper()} request for "
            f"{quantity} x {request.sku.name}"
            + (f" to {request.destination_site.name}" if request.destination_site else "")
            + "."
        ),
        section=requesting_section,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        meta={"request_id": request.id, "priority": priority.value},
    )

    await safe_broadcast(incident_id, "request.created", {"request": serialize(request)})
    return request


async def transition(
    session: AsyncSession,
    request: ResourceRequest,
    target: RequestState,
    *,
    actor: CurrentUser,
    correlation_id: str,
    note: str = "",
    ai_trace_id: str | None = None,
    broadcast: bool = True,
) -> ResourceRequest:
    """Move a request to ``target``, or raise :class:`IllegalTransition`."""
    current = RequestState(request.state)
    assert_transition(current, target)

    before = audit.snapshot(request)
    request.state = target
    request.updated_at = now()
    await session.flush()
    after = audit.snapshot(request)

    await audit.record(
        session,
        action=f"request.{target.value}",
        entity_type="resource_request",
        entity_id=request.id,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        before=before,
        after=after,
        ai_trace_id=ai_trace_id,
    )

    await activity.add(
        session,
        incident_id=request.incident_id,
        kind=ActivityKind.STATUS_CHANGE,
        body=(
            f"Request {request.id} moved {current.value} -> {target.value}"
            f" by {actor.display_name}." + (f" {note}" if note else "")
        ),
        section=IcsSection.LOGISTICS,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        meta={"request_id": request.id, "from": current.value, "to": target.value},
        ai_trace_id=ai_trace_id,
        broadcast=broadcast,
    )

    if broadcast:
        await safe_broadcast(
            request.incident_id, "request.updated", {"request": serialize(request)}
        )
    return request
