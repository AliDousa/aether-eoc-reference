"""The equity floor must fail closed.

`knowledge/resource-allocation-equity-rules.md` §3 states the rule these tests
enforce: an allocation may not reduce a site with equity priority 4-5 to zero in
order to serve a lower-priority site. When the only remaining stock sits behind
that floor, the correct behaviour is a stated shortfall, not a quiet raid.
"""

from __future__ import annotations

import httpx

from app.agents.recommender import Candidate, Leg, plan_allocation, validate_legs
from app.enums import Priority
from conftest import auth, immediate_request, login


def test_fails_closed_when_only_source_is_a_high_equity_site() -> None:
    """The single high-need site must not be drained, even for IMMEDIATE."""
    only_high_need = [
        Candidate(
            site_id="site_south",
            site_name="Sector South Cooling Center",
            equity_priority=5,
            available=30,
            reorder_point=80,
        )
    ]

    plan = plan_allocation(
        requested=30, candidates=only_high_need, priority=Priority.IMMEDIATE
    )

    # Reserve floor is max(1, ceil(0.25 * 80)) = 20, so at most 10 may move.
    assert plan.allocated == 10
    assert plan.shortfall == 20
    assert plan.legs[0].available_after == 20, "The site must not reach zero."
    assert plan.equity.withheld, "The review must record what was protected."
    assert "equity floor" in plan.equity.withheld[0]["reason"].lower()
    # The shortfall is stated, never rounded away.
    assert any("Shortfall" in note for note in plan.notes)


def test_zero_stock_high_equity_site_yields_no_leg() -> None:
    """A site already at its floor contributes nothing rather than going negative."""
    plan = plan_allocation(
        requested=50,
        candidates=[
            Candidate(
                site_id="site_north",
                site_name="Sector North Cooling Center",
                equity_priority=5,
                available=1,
                reorder_point=80,
            )
        ],
        priority=Priority.IMMEDIATE,
    )
    assert plan.legs == []
    assert plan.allocated == 0
    assert plan.shortfall == 50


def test_execution_time_validation_catches_an_edited_plan() -> None:
    """A human edit is re-checked against the floor, not trusted."""
    candidates = [
        Candidate(
            site_id="site_south",
            site_name="Sector South Cooling Center",
            equity_priority=4,
            available=60,
            reorder_point=80,
        )
    ]
    # An operator hand-edits the plan to take everything.
    breaching = [Leg("site_south", "Sector South Cooling Center", 60, 4, 60, 0)]

    review = validate_legs(breaching, candidates)

    assert review.passed is False
    assert review.violations
    assert "floor requires at least" in review.violations[0]["reason"]

    # A movement that respects the floor passes.
    ok = validate_legs([Leg("site_south", "Sector South Cooling Center", 40, 4, 60, 20)], candidates)
    assert ok.passed is True


def test_reserve_sites_may_be_drawn_to_zero() -> None:
    """The floor protects populations, not warehouses."""
    plan = plan_allocation(
        requested=100,
        candidates=[
            Candidate("site_staging", "Field Staging", 1, 40, 20),
            Candidate("site_cache", "Central Cache", 2, 60, 100),
        ],
        priority=Priority.PRIORITY,
    )
    assert plan.allocated == 100
    assert plan.shortfall == 0
    # Both reserve sites may go to zero; that is what reserve stock is for.
    assert all(leg.available_after == 0 for leg in plan.legs)


async def test_api_refuses_a_breaching_edit(client: httpx.AsyncClient) -> None:
    """End to end: the API rejects an edited allocation that breaches the floor."""
    token = await login(client, "logistics.demo")
    request = await immediate_request(client)
    recommend = await client.post(
        f"/api/requests/{request['id']}/recommend", headers=auth(token)
    )
    recommendation = recommend.json()["request"]["recommendation"]

    # Find the high-equity source leg and demand every unit it holds.
    high_equity = [
        leg for leg in recommendation["payload"]["legs"] if leg["equity_priority"] >= 4
    ]
    assert high_equity, "The seeded scenario should include a protected source site."
    leg = high_equity[0]

    response = await client.post(
        f"/api/recommendations/{recommendation['id']}/decide",
        headers=auth(token),
        json={
            "decision": "modify",
            "reason": "Take everything they have.",
            "modified_legs": [
                {
                    "from_site_id": leg["from_site_id"],
                    "from_site_name": leg["from_site_name"],
                    "quantity": leg["available_before"],
                    "equity_priority": leg["equity_priority"],
                }
            ],
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "equity_guardrail"
    assert body["detail"]["violations"]
    # Logistics may not override; only an Incident Commander may.
    assert body["detail"]["override_allowed"] is False
