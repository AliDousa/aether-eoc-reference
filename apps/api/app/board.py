"""Board assembly: the single read model behind the incident screen.

The board is one endpoint rather than five because it is read on a timer and
after every WebSocket hint. Assembling it server-side keeps the client from
fanning out four requests and then reconciling four slightly different moments
in time — which, on a screen people make resource decisions from, is a
correctness concern and not just a performance one.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import activity
from app import requests as requests_service
from app.clock import iso
from app.enums import IcsSection, IncidentStatus, Priority, RecommendationStatus, RequestState
from app.models import Incident, InventoryPosition, Operator, Recommendation
from app.realtime import hub

# ICS sections shown as chips on the board header. Finance/Admin is present and
# read-only: the slice does not implement cost capture, and pretending
# otherwise would be worse than showing it unstaffed.
SECTION_CHIPS: tuple[tuple[IcsSection, str], ...] = (
    (IcsSection.COMMAND, "Command"),
    (IcsSection.OPERATIONS, "Operations"),
    (IcsSection.PLANNING, "Planning"),
    (IcsSection.LOGISTICS, "Logistics"),
    (IcsSection.FINANCE_ADMIN, "Finance / Admin"),
)

OPEN_STATES = {
    RequestState.DRAFT,
    RequestState.SUBMITTED,
    RequestState.RECOMMENDED,
    RequestState.APPROVED,
    RequestState.MODIFIED,
    RequestState.TASKED,
}


def serialize_incident(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        "name": incident.name,
        "type": incident.type,
        "severity": str(incident.severity),
        "status": str(incident.status),
        "activated_at": iso(incident.activated_at),
        "current_period": incident.current_period,
        "period_started_at": iso(incident.period_started_at),
        "period_ends_at": iso(incident.period_ends_at),
        "commander": {
            "id": incident.commander.id,
            "display_name": incident.commander.display_name,
            "ics_role": str(incident.commander.ics_role),
        }
        if incident.commander
        else None,
        "jurisdiction": incident.jurisdiction,
        "objectives": list(incident.objectives or []),
    }


async def _section_chips(session: AsyncSession) -> list[dict[str, Any]]:
    operators = list((await session.execute(select(Operator))).scalars())
    staffed = {IcsSection(op.section) for op in operators}
    return [
        {
            "section": section.value,
            "label": label,
            "staffed": section in staffed,
            "operator_count": sum(1 for op in operators if IcsSection(op.section) is section),
            # Finance/Admin is deliberately not implemented in this slice.
            "implemented": section is not IcsSection.FINANCE_ADMIN,
        }
        for section, label in SECTION_CHIPS
    ]


async def inventory_rows(session: AsyncSession) -> list[dict[str, Any]]:
    positions = list((await session.execute(select(InventoryPosition))).scalars())
    return [
        {
            "id": position.id,
            "site_id": position.site_id,
            "site_name": position.site.name,
            "site_kind": str(position.site.kind),
            "equity_priority": position.site.equity_priority,
            "sku_id": position.sku_id,
            "sku_code": position.sku.code,
            "sku_name": position.sku.name,
            "category": position.sku.category,
            "unit": position.sku.unit,
            "on_hand": position.on_hand,
            "reserved": position.reserved,
            "available": position.available,
            "reorder_point": position.reorder_point,
            "below_reorder": position.below_reorder,
            "updated_at": iso(position.updated_at),
        }
        for position in positions
    ]


async def build(session: AsyncSession, incident: Incident) -> dict[str, Any]:
    requests = await requests_service.list_for_incident(session, incident.id)
    open_requests = [r for r in requests if RequestState(r.state) in OPEN_STATES]

    unfilled_immediate = sum(
        1
        for request in open_requests
        if Priority(request.priority) is Priority.IMMEDIATE
        and RequestState(request.state) in {RequestState.SUBMITTED, RequestState.RECOMMENDED}
    )

    positions = await inventory_rows(session)
    below_reorder = [row for row in positions if row["below_reorder"]]

    pending_reviews = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Recommendation)
                .where(Recommendation.status == RecommendationStatus.PENDING)
            )
        ).scalar_one()
    )

    events = await activity.recent(session, incident.id, limit=40)

    # Attach the latest recommendation to each request so the table can show a
    # "needs decision" marker without an N+1 fetch from the client.
    recommendations = list(
        (
            await session.execute(select(Recommendation).order_by(Recommendation.created_at.desc()))
        ).scalars()
    )
    latest_by_request: dict[str, Recommendation] = {}
    for recommendation in recommendations:
        latest_by_request.setdefault(recommendation.request_id, recommendation)

    return {
        "incident": serialize_incident(incident),
        "status_note": (
            "Demobilising"
            if IncidentStatus(incident.status) is IncidentStatus.DEMOBILIZING
            else None
        ),
        "sections": await _section_chips(session),
        "kpis": {
            "open_requests": len(open_requests),
            "unfilled_immediate": unfilled_immediate,
            # Distinct sites, not site x SKU lines — the label says "sites",
            # and a single site short on four items is one problem to solve.
            "sites_below_reorder": len({row["site_id"] for row in below_reorder}),
            "lines_below_reorder": len(below_reorder),
            "pending_ai_reviews": pending_reviews,
        },
        "requests": [
            requests_service.serialize(request, recommendation=latest_by_request.get(request.id))
            for request in requests
        ],
        "activity": [activity.serialize(event) for event in events],
        "inventory": positions,
        "below_reorder": below_reorder,
        "presence": hub.presence(incident.id),
    }


async def current_incident(session: AsyncSession) -> Incident | None:
    """The one seeded incident.

    This slice models a single active incident on purpose (docs/PRODUCT.md);
    multi-incident routing is an explicit non-goal.
    """
    stmt = select(Incident).order_by(Incident.activated_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()
