"""Inventory movement: the single mutation point for stock.

Nothing else in the codebase writes ``InventoryPosition.on_hand``. Agents
propose; only :func:`transfer` moves anything, and it always writes the
matching audit row in the same transaction. If you are reviewing this repo for
the guardrail story, this module and ``app.audit`` are the two files that
matter.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.clock import now
from app.errors import InsufficientStock, NotFound
from app.ids import new_id
from app.models import AuditEvent, InventoryPosition, ResourceSite, Sku


@dataclass(frozen=True)
class Allocation:
    """One leg of a movement: take ``quantity`` of a SKU from one site."""

    from_site_id: str
    quantity: int


async def get_position(
    session: AsyncSession, site_id: str, sku_id: str
) -> InventoryPosition | None:
    stmt = select(InventoryPosition).where(
        InventoryPosition.site_id == site_id, InventoryPosition.sku_id == sku_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_position(session: AsyncSession, site_id: str, sku_id: str) -> InventoryPosition:
    """Return the position for a site/SKU pair, creating an empty one if absent.

    A destination site legitimately may never have stocked this SKU before;
    that is a normal first delivery, not an error.
    """
    position = await get_position(session, site_id, sku_id)
    if position is not None:
        return position

    if not await session.get(ResourceSite, site_id):
        raise NotFound(f"Unknown site '{site_id}'.")
    if not await session.get(Sku, sku_id):
        raise NotFound(f"Unknown SKU '{sku_id}'.")

    position = InventoryPosition(
        id=new_id("inv"),
        site_id=site_id,
        sku_id=sku_id,
        on_hand=0,
        reserved=0,
        reorder_point=0,
        updated_at=now(),
    )
    session.add(position)
    await session.flush()
    return position


async def positions_for_sku(session: AsyncSession, sku_id: str) -> list[InventoryPosition]:
    stmt = select(InventoryPosition).where(InventoryPosition.sku_id == sku_id)
    return list((await session.execute(stmt)).scalars())


async def all_positions(session: AsyncSession) -> list[InventoryPosition]:
    stmt = select(InventoryPosition).order_by(InventoryPosition.site_id)
    return list((await session.execute(stmt)).scalars())


async def transfer(
    session: AsyncSession,
    *,
    sku_id: str,
    from_site_id: str,
    to_site_id: str,
    quantity: int,
    actor_id: str,
    actor_label: str,
    correlation_id: str,
    reason: str,
    ai_trace_id: str | None = None,
) -> AuditEvent:
    """Move ``quantity`` of one SKU between two sites and audit the move.

    Fails closed: an oversized movement raises before anything is written, so a
    partially-applied multi-leg allocation is not possible within a request.

    Returns the audit row so callers can count writes (the approval path is
    asserted to produce exactly one inventory row per leg).
    """
    if quantity <= 0:
        raise InsufficientStock(
            "Transfer quantity must be positive.", detail={"quantity": quantity}
        )
    if from_site_id == to_site_id:
        raise InsufficientStock(
            "Source and destination sites are the same.", detail={"site_id": from_site_id}
        )

    source = await get_position(session, from_site_id, sku_id)
    if source is None:
        raise NotFound(
            "Source site holds no position for this SKU.",
            detail={"site_id": from_site_id, "sku_id": sku_id},
        )
    if source.available < quantity:
        raise InsufficientStock(
            "Source site does not have enough available stock.",
            detail={
                "site_id": from_site_id,
                "sku_id": sku_id,
                "requested": quantity,
                "available": source.available,
            },
        )

    destination = await ensure_position(session, to_site_id, sku_id)

    before = {
        "source": audit.snapshot(source),
        "destination": audit.snapshot(destination),
    }

    source.on_hand -= quantity
    source.updated_at = now()
    destination.on_hand += quantity
    destination.updated_at = now()
    await session.flush()

    after = {
        "source": audit.snapshot(source),
        "destination": audit.snapshot(destination),
    }

    return await audit.record(
        session,
        action="inventory.transfer",
        entity_type="inventory_position",
        entity_id=destination.id,
        correlation_id=correlation_id,
        actor_id=actor_id,
        actor_label=actor_label,
        before=before,
        after=after | {"reason": reason, "quantity": quantity, "sku_id": sku_id},
        ai_trace_id=ai_trace_id,
    )
