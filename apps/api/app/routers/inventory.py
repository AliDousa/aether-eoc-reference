"""Inventory, sites, and catalogue — all read-only.

There is no write endpoint here on purpose. Stock moves only as the result of a
human decision on a recommendation (``/api/recommendations/{id}/decide``), which
routes through ``app.inventory.transfer`` and writes the audit row in the same
transaction. Adding a direct "adjust stock" route would create a second path to
the one thing this repository is arguing should have exactly one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app import board
from app.clock import iso
from app.deps import DbSession
from app.models import ResourceSite, Sku

router = APIRouter(prefix="/api", tags=["inventory"])


@router.get("/inventory")
async def list_inventory(session: DbSession) -> dict[str, Any]:
    rows = await board.inventory_rows(session)
    return {
        "positions": rows,
        "below_reorder": [row for row in rows if row["below_reorder"]],
    }


@router.get("/sites")
async def list_sites(session: DbSession) -> dict[str, Any]:
    sites = list(
        (await session.execute(select(ResourceSite).order_by(ResourceSite.name))).scalars()
    )
    return {
        "sites": [
            {
                "id": site.id,
                "name": site.name,
                "kind": str(site.kind),
                "lat": site.lat,
                "lon": site.lon,
                "equity_priority": site.equity_priority,
                "notes": site.notes,
                "created_at": iso(site.created_at),
            }
            for site in sites
        ]
    }


@router.get("/skus")
async def list_skus(session: DbSession) -> dict[str, Any]:
    skus = list((await session.execute(select(Sku).order_by(Sku.category, Sku.name))).scalars())
    return {
        "skus": [
            {
                "id": sku.id,
                "code": sku.code,
                "name": sku.name,
                "category": sku.category,
                "unit": sku.unit,
            }
            for sku in skus
        ]
    }
