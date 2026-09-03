"""Incident activity stream.

Append-only, like the audit log, but for a different audience: the audit log is
for accountability after the fact, the activity stream is the operational
narrative people read during the incident. Every entry here is human-readable;
every entry in ``app.audit`` is machine-verifiable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.clock import iso, now
from app.enums import ActivityKind, IcsSection
from app.ids import new_id
from app.models import ActivityEvent
from app.realtime import safe_broadcast


def serialize(event: ActivityEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "incident_id": event.incident_id,
        "actor_id": event.actor_id,
        "actor_name": event.actor.display_name if event.actor else "SYSTEM",
        "kind": event.kind.value if isinstance(event.kind, ActivityKind) else str(event.kind),
        "body": event.body,
        "section": event.section.value if isinstance(event.section, IcsSection) else event.section,
        "meta": event.meta or {},
        "created_at": iso(event.created_at),
    }


async def add(
    session: AsyncSession,
    *,
    incident_id: str,
    kind: ActivityKind,
    body: str,
    correlation_id: str,
    actor_id: str | None = None,
    actor_label: str = "SYSTEM",
    section: IcsSection | None = None,
    meta: dict[str, Any] | None = None,
    audit_action: str | None = None,
    ai_trace_id: str | None = None,
    broadcast: bool = True,
) -> ActivityEvent:
    """Append one activity entry and push it to connected boards.

    An audit row is written only when ``audit_action`` is supplied, i.e. when
    this entry *is* the primary action (a human posting a log note). Entries
    that merely narrate something already audited — a state transition, an
    agent run — pass no action, because duplicating them would bury the
    ``ai.*`` and ``inventory.*`` rows that the audit log exists to make
    findable.

    The broadcast is best-effort and cannot fail the caller: a note that is
    written but not yet pushed is recoverable, a note that fails to write
    because a socket died is not.
    """
    event = ActivityEvent(
        id=new_id("act"),
        incident_id=incident_id,
        actor_id=actor_id,
        kind=kind,
        body=body,
        section=section,
        meta=meta or {},
        created_at=now(),
    )
    session.add(event)
    await session.flush()

    if audit_action:
        await audit.record(
            session,
            action=audit_action,
            entity_type="activity_event",
            entity_id=event.id,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_label=actor_label,
            after={"kind": kind.value, "body": body, "meta": event.meta},
            ai_trace_id=ai_trace_id,
        )

    if broadcast:
        await session.refresh(event)
        await safe_broadcast(incident_id, "activity.created", {"event": serialize(event)})

    return event


async def recent(
    session: AsyncSession, incident_id: str, *, limit: int = 50
) -> list[ActivityEvent]:
    """Most recent entries first — the order the board reads them in."""
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.incident_id == incident_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())
