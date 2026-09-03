"""Append-only, hash-chained audit log.

Every state change in the system funnels through :func:`record`. Each row
commits to the row before it:

    hash(n) = SHA256( hash(n-1) || canonical_json(row(n)) )

Editing or deleting a historical row therefore invalidates every row after it,
which :func:`verify_chain` detects and ``GET /api/audit/verify`` exposes. This
is tamper *evidence*, not tamper *proofing*: anyone who can write the database
can also recompute the chain. Making that distinction honestly is the point —
see ADR-0004 and docs/THREAT_MODEL.md.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import iso, now
from app.ids import new_id
from app.models import AuditEvent

# The chain has to start somewhere. 64 zeroes is conventional and makes the
# first row visually obvious in the audit table.
GENESIS_HASH = "0" * 64

# Serialises chain appends within this process. The hash of row N depends on
# row N-1, so two concurrent writers could otherwise read the same predecessor
# and produce a fork. A multi-process deployment needs a database-level
# sequence instead; ADR-0004 records that trade-off.
_chain_lock = asyncio.Lock()


def _json_safe(value: Any) -> Any:
    """Convert ORM/enum/datetime values into something json.dumps accepts."""
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def snapshot(obj: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialise an ORM instance to a JSON-safe dict of its mapped columns.

    Used for the ``before``/``after`` pair so a reviewer can diff exactly what
    changed without the audit call sites hand-listing fields (and drifting).
    """
    exclude = exclude or set()
    mapper = inspect(obj).mapper
    return {
        attr.key: _json_safe(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in exclude
    }


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON encoding.

    Sorted keys and no whitespace, so the same logical row always hashes to the
    same digest regardless of dict ordering or Python version.
    """
    return json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"))


def hash_row(prev_hash: str, row: dict[str, Any]) -> str:
    material = f"{prev_hash}|{canonical_json(row)}".encode()
    return hashlib.sha256(material).hexdigest()


def _hashable_fields(event: AuditEvent) -> dict[str, Any]:
    """The subset of a row that the chain commits to.

    ``seq`` is excluded because it is assigned by the database; everything a
    caller controls is included.
    """
    return {
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
    }


async def _last_hash(session: AsyncSession) -> str:
    stmt = select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() or GENESIS_HASH


async def record(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    correlation_id: str,
    actor_id: str | None = None,
    actor_label: str = "system",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ai_trace_id: str | None = None,
) -> AuditEvent:
    """Append one audit row and return it.

    Flushes but does not commit: the audit row joins the same transaction as
    the change it describes, so a rolled-back mutation cannot leave an orphan
    audit entry claiming it happened.
    """
    async with _chain_lock:
        prev = await _last_hash(session)
        event = AuditEvent(
            id=new_id("aud"),
            at=now(),
            actor_id=actor_id,
            actor_label=actor_label,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=_json_safe(before) if before is not None else None,
            after_json=_json_safe(after) if after is not None else None,
            correlation_id=correlation_id,
            ai_trace_id=ai_trace_id,
            prev_hash=prev,
            hash="",
        )
        event.hash = hash_row(prev, _hashable_fields(event))
        session.add(event)
        await session.flush()
        return event


@dataclass
class ChainVerification:
    """Result of replaying the audit chain from genesis."""

    ok: bool
    checked: int
    head_hash: str
    genesis_hash: str = GENESIS_HASH
    broken_at_seq: int | None = None
    detail: str = ""
    # Populated only on failure, so the API can say *what* failed.
    problems: list[str] = field(default_factory=list)


async def verify_chain(session: AsyncSession) -> ChainVerification:
    """Recompute every hash in order and report the first divergence."""
    stmt = select(AuditEvent).order_by(AuditEvent.seq.asc())
    events = list((await session.execute(stmt)).scalars())

    if not events:
        return ChainVerification(
            ok=True, checked=0, head_hash=GENESIS_HASH, detail="Audit log is empty."
        )

    expected_prev = GENESIS_HASH
    for event in events:
        if event.prev_hash != expected_prev:
            return ChainVerification(
                ok=False,
                checked=len(events),
                head_hash=events[-1].hash,
                broken_at_seq=event.seq,
                detail=f"Row {event.seq} does not link to its predecessor.",
                problems=[f"prev_hash mismatch at seq={event.seq} (id={event.id})"],
            )
        recomputed = hash_row(event.prev_hash, _hashable_fields(event))
        if recomputed != event.hash:
            return ChainVerification(
                ok=False,
                checked=len(events),
                head_hash=events[-1].hash,
                broken_at_seq=event.seq,
                detail=f"Row {event.seq} content does not match its hash.",
                problems=[f"hash mismatch at seq={event.seq} (id={event.id})"],
            )
        expected_prev = event.hash

    return ChainVerification(
        ok=True,
        checked=len(events),
        head_hash=events[-1].hash,
        detail=f"Verified {len(events)} rows from genesis.",
    )
