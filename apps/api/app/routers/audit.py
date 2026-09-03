"""Audit log: filterable read and chain verification.

Read-only by construction. There is no endpoint that writes, edits, or deletes
an audit row — rows appear only as a side effect of the action they describe.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app import audit as audit_service
from app.clock import iso
from app.deps import DbSession
from app.models import AuditEvent
from app.schemas import ChainVerificationResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _serialize(event: AuditEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "id": event.id,
        "at": iso(event.at),
        "actor_id": event.actor_id,
        "actor_label": event.actor_label,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "before": event.before_json,
        "after": event.after_json,
        "correlation_id": event.correlation_id,
        "ai_trace_id": event.ai_trace_id,
        "prev_hash": event.prev_hash,
        "hash": event.hash,
    }


@router.get("")
async def list_audit(
    session: DbSession,
    action_prefix: str | None = Query(
        default=None,
        description="Filter by dotted action namespace, e.g. 'ai.' or 'inventory.'",
    ),
    entity_id: str | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    stmt = select(AuditEvent)
    count_stmt = select(func.count()).select_from(AuditEvent)

    if action_prefix:
        # Prefix match so the UI's 'ai.*' and 'inventory.*' filters work with a
        # single parameter rather than an enumerated list of actions.
        pattern = f"{action_prefix.rstrip('*')}%"
        stmt = stmt.where(AuditEvent.action.like(pattern))
        count_stmt = count_stmt.where(AuditEvent.action.like(pattern))
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
        count_stmt = count_stmt.where(AuditEvent.entity_id == entity_id)
    if correlation_id:
        stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
        count_stmt = count_stmt.where(AuditEvent.correlation_id == correlation_id)

    total = int((await session.execute(count_stmt)).scalar_one())
    stmt = stmt.order_by(AuditEvent.seq.desc()).limit(limit).offset(offset)
    events = list((await session.execute(stmt)).scalars())

    actions = list(
        (
            await session.execute(
                select(AuditEvent.action, func.count())
                .group_by(AuditEvent.action)
                .order_by(AuditEvent.action)
            )
        ).all()
    )

    return {
        "events": [_serialize(event) for event in events],
        "total": total,
        "limit": limit,
        "offset": offset,
        "action_counts": [{"action": action, "count": count} for action, count in actions],
    }


@router.get("/verify", response_model=ChainVerificationResponse)
async def verify(session: DbSession) -> ChainVerificationResponse:
    """Replay the hash chain from genesis and report the first divergence.

    This is what makes "immutable audit log" a checkable claim. It is tamper
    *evidence*: anyone who can write the database can also recompute the chain,
    which docs/THREAT_MODEL.md states plainly.
    """
    result = await audit_service.verify_chain(session)
    return ChainVerificationResponse(
        ok=result.ok,
        checked=result.checked,
        head_hash=result.head_hash,
        genesis_hash=result.genesis_hash,
        broken_at_seq=result.broken_at_seq,
        detail=result.detail,
        problems=result.problems,
    )
