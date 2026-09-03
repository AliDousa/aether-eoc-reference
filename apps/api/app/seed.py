"""Seed the synthetic heat-surge scenario.

    uv run python -m app.seed          # create and populate
    uv run python -m app.seed --reset  # drop everything first

The interesting decision here is that the seeder does **not** insert history
rows directly. It replays ``fixtures/timeline.json`` through the same service
functions the running application uses — ``requests.create``,
``supervisor.run_intent``, ``decisions.approve``, ``decisions.reject``.

That costs a little complexity and buys a lot of honesty: the seeded audit log
is produced by the real code path, its hash chain verifies like any other, and
the demo cannot drift away from the application's actual behaviour. If a
transition becomes illegal, seeding fails loudly instead of quietly writing a
history the app could never have produced.

The seeding clock (``app.clock``) is wound back six hours and stepped forward
through the script, so the incident has a believable timeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select

from app import clock, decisions
from app import requests as requests_service
from app.activity import add as add_activity
from app.agents import supervisor
from app.config import get_settings
from app.db import create_all, dispose_engine, get_session_factory
from app.enums import (
    ActivityKind,
    IcsRole,
    IcsSection,
    IncidentStatus,
    Priority,
    Severity,
    SiteKind,
)
from app.ids import correlation_id
from app.models import (
    ActivityEvent,
    AgentRun,
    AuditEvent,
    Incident,
    InventoryPosition,
    Operator,
    Recommendation,
    ResourceRequest,
    ResourceSite,
    Sku,
)
from app.security import CurrentUser, hash_password

DEMO_PASSWORD = "demo"


def _load(name: str) -> dict[str, Any]:
    path = get_settings().fixtures_dir / name
    if not path.is_file():
        raise SystemExit(f"Missing fixture: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _as_user(operator: Operator) -> CurrentUser:
    return CurrentUser(
        id=operator.id,
        username=operator.username,
        display_name=operator.display_name,
        ics_role=IcsRole(operator.ics_role),
        section=IcsSection(operator.section),
    )


async def _wipe() -> None:
    """Delete all rows, newest tables first to respect foreign keys."""
    factory = get_session_factory()
    async with factory() as session:
        for model in (
            AuditEvent,
            ActivityEvent,
            Recommendation,
            AgentRun,
            ResourceRequest,
            InventoryPosition,
            Incident,
            Sku,
            ResourceSite,
            Operator,
        ):
            await session.execute(delete(model))
        await session.commit()


async def _seed_reference_data() -> tuple[Incident, dict[str, Operator]]:
    """Insert operators, incident, sites, SKUs, and opening stock."""
    factory = get_session_factory()
    operators_fixture = _load("operators.json")
    incident_fixture = _load("incident.json")["incident"]
    sites_fixture = _load("sites.json")["sites"]
    skus_fixture = _load("skus.json")["skus"]
    inventory_fixture = _load("inventory.json")["positions"]

    password_hash = hash_password(operators_fixture.get("demo_password", DEMO_PASSWORD))
    activated_at = clock.now()

    async with factory() as session:
        operators: dict[str, Operator] = {}
        for row in operators_fixture["operators"]:
            operator = Operator(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                ics_role=IcsRole(row["ics_role"]),
                section=IcsSection(row["section"]),
                password_hash=password_hash,
                is_demo=True,
                created_at=activated_at,
            )
            session.add(operator)
            operators[row["id"]] = operator

        for row in sites_fixture:
            session.add(
                ResourceSite(
                    id=row["id"],
                    name=row["name"],
                    kind=SiteKind(row["kind"]),
                    lat=row["lat"],
                    lon=row["lon"],
                    equity_priority=row["equity_priority"],
                    notes=row.get("notes", ""),
                    created_at=activated_at,
                )
            )

        for row in skus_fixture:
            session.add(
                Sku(
                    id=row["id"],
                    code=row["code"],
                    name=row["name"],
                    category=row["category"],
                    unit=row["unit"],
                    created_at=activated_at,
                )
            )
        await session.flush()

        period_hours = int(incident_fixture.get("period_hours", 12))
        period_started = activated_at + timedelta(
            hours=incident_fixture.get("activated_hours_ago", 6)
            - incident_fixture.get("period_started_hours_ago", 2)
        )
        incident = Incident(
            id=incident_fixture["id"],
            name=incident_fixture["name"],
            type=incident_fixture["type"],
            severity=Severity(incident_fixture["severity"]),
            status=IncidentStatus(incident_fixture["status"]),
            activated_at=activated_at,
            current_period=incident_fixture["current_period"],
            period_started_at=period_started,
            period_ends_at=period_started + timedelta(hours=period_hours),
            commander_operator_id=incident_fixture["commander_operator_id"],
            jurisdiction=incident_fixture["jurisdiction"],
            objectives=list(incident_fixture.get("objectives", [])),
            created_at=activated_at,
        )
        session.add(incident)

        for index, row in enumerate(inventory_fixture):
            session.add(
                InventoryPosition(
                    id=f"inv_{index:03d}",
                    site_id=row["site_id"],
                    sku_id=row["sku_id"],
                    on_hand=row["on_hand"],
                    reserved=row["reserved"],
                    reorder_point=row["reorder_point"],
                    updated_at=activated_at,
                )
            )

        await session.commit()
        return incident, operators


async def _replay_timeline(incident_id: str) -> None:
    """Apply the scripted history through the real service functions."""
    steps = _load("timeline.json")["steps"]
    factory = get_session_factory()
    # Maps a timeline `ref` onto the id the service actually generated.
    created: dict[str, str] = {}
    base_offset = timedelta(hours=-6)

    for step in steps:
        clock.set_offset(base_offset + timedelta(minutes=step["at_minutes"]))
        correlation = correlation_id()

        async with factory() as session:
            operator = await session.get(Operator, step["actor"])
            if operator is None:
                raise SystemExit(f"Timeline references unknown operator '{step['actor']}'.")
            actor = _as_user(operator)
            kind = step["kind"]

            if kind == "note":
                await add_activity(
                    session,
                    incident_id=incident_id,
                    kind=ActivityKind.LOG_NOTE,
                    body=step["body"],
                    section=IcsSection(step["section"]),
                    correlation_id=correlation,
                    actor_id=actor.id,
                    actor_label=actor.label,
                    audit_action="activity.note_posted",
                    broadcast=False,
                )

            elif kind == "request":
                request = await requests_service.create(
                    session,
                    incident_id=incident_id,
                    sku_id=step["sku_id"],
                    quantity=step["quantity"],
                    priority=Priority(step["priority"]),
                    requesting_section=IcsSection(step["section"]),
                    justification=step["justification"],
                    destination_site_id=step["destination"],
                    actor=actor,
                    correlation_id=correlation,
                )
                created[step["ref"]] = request.id

            elif kind == "recommend":
                await supervisor.run_intent(
                    session,
                    incident_id=incident_id,
                    intent="resource_recommendation",
                    actor=actor,
                    correlation_id=correlation,
                    request_id=created[step["ref"]],
                )

            elif kind in {"approve", "reject"}:
                recommendation = await requests_service.latest_recommendation(
                    session, created[step["ref"]]
                )
                if recommendation is None:
                    raise SystemExit(f"Timeline step '{kind}' has no recommendation to decide.")
                if kind == "approve":
                    await decisions.approve(
                        session,
                        recommendation,
                        actor=actor,
                        correlation_id=correlation,
                        reason=step.get("reason", ""),
                    )
                else:
                    await decisions.reject(
                        session,
                        recommendation,
                        actor=actor,
                        correlation_id=correlation,
                        reason=step["reason"],
                    )
            else:
                raise SystemExit(f"Unknown timeline step kind '{kind}'.")

            await session.commit()

    clock.reset_offset()


async def _report() -> None:
    from app.audit import verify_chain

    factory = get_session_factory()
    async with factory() as session:
        counts = {}
        for label, model in (
            ("operators", Operator),
            ("sites", ResourceSite),
            ("skus", Sku),
            ("inventory positions", InventoryPosition),
            ("activity events", ActivityEvent),
            ("resource requests", ResourceRequest),
            ("agent runs", AgentRun),
            ("recommendations", Recommendation),
            ("audit events", AuditEvent),
        ):
            rows = (await session.execute(select(model))).scalars().all()
            counts[label] = len(rows)

        verification = await verify_chain(session)
        requests = (await session.execute(select(ResourceRequest))).scalars().all()

    print("\nSeeded HEAT-2026-DUBAI-REF")
    print("-" * 52)
    for label, count in counts.items():
        print(f"  {label:<22} {count}")
    print("-" * 52)
    print(
        f"  audit chain            {'VERIFIED' if verification.ok else 'BROKEN'} "
        f"({verification.checked} rows)"
    )
    print("\n  Requests:")
    for request in sorted(requests, key=lambda r: r.created_at):
        print(
            f"    {request.id}  {str(request.state):<12} {str(request.priority):<10} "
            f"{request.quantity:>4} x {request.sku_id}"
        )
    print("\nDemo logins (password: demo): ic.demo | ops.demo | logistics.demo\n")


async def main(reset: bool, *, quiet: bool = False) -> None:
    settings = get_settings()
    if not quiet:
        print(f"Database: {settings.sqlalchemy_url}")
    await create_all()
    if reset:
        await _wipe()
    else:
        factory = get_session_factory()
        async with factory() as session:
            existing = (await session.execute(select(Incident))).scalars().first()
        if existing is not None:
            if not quiet:
                print(
                    f"Incident '{existing.name}' is already seeded. "
                    "Re-run with --reset to rebuild from fixtures."
                )
            await dispose_engine()
            return

    clock.set_offset(timedelta(hours=-6))
    try:
        incident, _ = await _seed_reference_data()
        await _replay_timeline(incident.id)
    finally:
        clock.reset_offset()

    if not quiet:
        await _report()
    await dispose_engine()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic EOC scenario.")
    parser.add_argument("--reset", action="store_true", help="Delete existing rows before seeding.")
    args = parser.parse_args()
    try:
        asyncio.run(main(reset=args.reset))
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)


if __name__ == "__main__":
    cli()
