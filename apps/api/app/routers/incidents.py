"""Incident board and activity stream."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import activity, board
from app.deps import CorrelationDep, CurrentUserDep, DbSession
from app.enums import ActivityKind, IcsSection
from app.errors import NotFound
from app.models import Incident
from app.schemas import ActivityNoteRequest
from app.security import Permission, require

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


async def _require_incident(session: DbSession, incident_id: str) -> Incident:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise NotFound(f"Unknown incident '{incident_id}'.")
    return incident


@router.get("/current")
async def current(session: DbSession) -> dict[str, Any]:
    """The active incident's full board.

    Readable without a token: the board is the first thing a reviewer should
    see, and requiring login to view a synthetic demo adds friction without
    adding safety. Every *write* endpoint requires authentication.
    """
    incident = await board.current_incident(session)
    if incident is None:
        raise NotFound("No incident has been seeded. Run `make seed`.")
    return await board.build(session, incident)


@router.get("/{incident_id}/board")
async def get_board(incident_id: str, session: DbSession) -> dict[str, Any]:
    incident = await _require_incident(session, incident_id)
    return await board.build(session, incident)


@router.get("/{incident_id}/activity")
async def get_activity(incident_id: str, session: DbSession, limit: int = 50) -> dict[str, Any]:
    await _require_incident(session, incident_id)
    events = await activity.recent(session, incident_id, limit=min(max(limit, 1), 200))
    return {"events": [activity.serialize(event) for event in events]}


@router.post("/{incident_id}/activity", status_code=201)
async def post_note(
    incident_id: str,
    body: ActivityNoteRequest,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    """Post a log note.

    Every authenticated role may do this, including Operations — posting to the
    incident log is not the same authority as committing resources.
    """
    require(user, Permission.POST_ACTIVITY)
    incident = await _require_incident(session, incident_id)

    event = await activity.add(
        session,
        incident_id=incident.id,
        kind=ActivityKind.LOG_NOTE,
        body=body.body.strip(),
        section=body.section or IcsSection(user.section),
        correlation_id=correlation_id,
        actor_id=user.id,
        actor_label=user.label,
        audit_action="activity.note_posted",
    )
    await session.commit()
    await session.refresh(event)
    return {"event": activity.serialize(event)}
