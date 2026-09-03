"""The central claim of this repository: an agent proposes, a human commits.

If either of these tests fails, the guardrail story is false.
"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, InventoryPosition
from conftest import auth, immediate_request, login


async def _ors_positions(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(
        select(InventoryPosition).where(InventoryPosition.sku_id == "sku_ors")
    )
    return {position.site_id: position.on_hand for position in rows.scalars()}


async def test_recommendation_does_not_mutate_inventory(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Running the recommender must change nothing but the request's state."""
    token = await login(client, "logistics.demo")
    request = await immediate_request(client)

    before = await _ors_positions(session)

    response = await client.post(
        f"/api/requests/{request['id']}/recommend", headers=auth(token)
    )
    assert response.status_code == 200
    payload = response.json()

    # A plan was produced, and it is explicitly held for a human.
    recommendation = payload["request"]["recommendation"]
    assert recommendation["status"] == "pending"
    assert payload["result"]["requires_human"] is True
    assert payload["request"]["state"] == "recommended"
    # The scenario is built so this cannot be filled from one site.
    assert len(recommendation["payload"]["legs"]) > 1
    assert recommendation["payload"]["shortfall"] > 0

    session.expire_all()
    after = await _ors_positions(session)
    assert after == before, "The recommender must not move stock."

    # And no inventory audit row was written by the agent path.
    inventory_rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "inventory.transfer")
        )
    ).scalars().all()
    # Only the two transfers from the seeded, already-approved water request.
    assert len(inventory_rows) == 2


async def test_approval_moves_stock_once_and_audits_decision_and_transfer(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """The approve path writes exactly one transfer per leg, plus a decision row."""
    token = await login(client, "logistics.demo")
    request = await immediate_request(client)

    recommend = await client.post(
        f"/api/requests/{request['id']}/recommend", headers=auth(token)
    )
    recommendation = recommend.json()["request"]["recommendation"]

    # Approve a single-leg subset so the counting assertion is unambiguous.
    first_leg = recommendation["payload"]["legs"][0]
    before = await _ors_positions(session)
    baseline_transfers = len(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "inventory.transfer")
            )
        )
        .scalars()
        .all()
    )

    decide = await client.post(
        f"/api/recommendations/{recommendation['id']}/decide",
        headers=auth(token),
        json={
            "decision": "modify",
            "reason": "Taking the first leg only; holding the rest for OP-3.",
            "modified_legs": [
                {
                    "from_site_id": first_leg["from_site_id"],
                    "from_site_name": first_leg["from_site_name"],
                    "quantity": first_leg["quantity"],
                    "equity_priority": first_leg["equity_priority"],
                }
            ],
        },
    )
    assert decide.status_code == 200
    outcome = decide.json()

    # Exactly one inventory audit row for this decision...
    assert len(outcome["audit"]["inventory_event_ids"]) == 1
    # ...and a decision row alongside it. Both are required by the brief.
    assert outcome["audit"]["decision_event_id"]

    session.expire_all()
    after = await _ors_positions(session)
    moved = first_leg["quantity"]
    assert after[first_leg["from_site_id"]] == before[first_leg["from_site_id"]] - moved
    destination = request["destination_site"]["id"]
    assert after[destination] == before[destination] + moved
    assert outcome["moved_total"] == moved

    transfers = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "inventory.transfer")
        )
    ).scalars().all()
    assert len(transfers) == baseline_transfers + 1, "Stock must move exactly once."

    decisions = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "recommendation.modified")
        )
    ).scalars().all()
    assert len(decisions) == 1

    # The audit chain still verifies after the write.
    verify = (await client.get("/api/audit/verify")).json()
    assert verify["ok"] is True


async def test_operations_cannot_commit_resources(client: httpx.AsyncClient) -> None:
    """RBAC is enforced server-side, not merely hidden in the UI."""
    logistics = await login(client, "logistics.demo")
    request = await immediate_request(client)
    recommend = await client.post(
        f"/api/requests/{request['id']}/recommend", headers=auth(logistics)
    )
    recommendation_id = recommend.json()["request"]["recommendation"]["id"]

    operations = await login(client, "ops.demo")
    response = await client.post(
        f"/api/recommendations/{recommendation_id}/decide",
        headers=auth(operations),
        json={"decision": "approve", "reason": "attempting without authority"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
