"""Human decisions on agent recommendations.

This module is the hinge the whole repository turns on. An agent produced a
plan; nothing has happened yet. Here a person with the right ICS authority
accepts it, edits it, or refuses it — and only here does stock actually move,
by calling ``app.inventory.transfer``.

Three properties worth checking while reading:

* Authority is verified before anything else (``require_decision_authority``).
* The equity floor is re-evaluated against **current** stock at execution
  time, not trusted from the proposal. An edited plan gets the same scrutiny
  as a generated one, and a stale plan cannot slip through.
* A breach can only be overridden by an Incident Commander, and only with a
  written reason, exactly as ``knowledge/resource-allocation-equity-rules.md``
  §3 requires. The system cannot override itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import activity, audit, inventory
from app import requests as requests_service
from app.agents.recommender import Candidate, Leg, validate_legs
from app.clock import now
from app.enums import (
    ActivityKind,
    AgentName,
    IcsSection,
    RecommendationStatus,
    RequestState,
)
from app.errors import DomainError, EquityGuardrailViolation, NotFound
from app.models import AuditEvent, InventoryPosition, Recommendation, ResourceRequest
from app.realtime import safe_broadcast
from app.security import CurrentUser, Permission, has_permission, require_decision_authority


class DecisionError(DomainError):
    status_code = 409
    code = "decision_error"


@dataclass
class DecisionOutcome:
    recommendation: Recommendation
    request: ResourceRequest
    inventory_audit_events: list[AuditEvent]
    decision_audit_event: AuditEvent
    moved_total: int


def _legs_from_payload(payload: dict[str, Any]) -> list[Leg]:
    return [
        Leg(
            from_site_id=str(leg["from_site_id"]),
            from_site_name=str(leg.get("from_site_name", leg["from_site_id"])),
            quantity=int(leg["quantity"]),
            equity_priority=int(leg.get("equity_priority", 3)),
            available_before=int(leg.get("available_before", 0)),
            available_after=int(leg.get("available_after", 0)),
        )
        for leg in payload.get("legs", [])
    ]


async def _current_candidates(session: AsyncSession, request: ResourceRequest) -> list[Candidate]:
    """Live stock for the request's SKU, excluding the destination site."""
    stmt = select(InventoryPosition).where(InventoryPosition.sku_id == request.sku_id)
    positions = list((await session.execute(stmt)).scalars())
    return [
        Candidate(
            site_id=position.site_id,
            site_name=position.site.name,
            equity_priority=position.site.equity_priority,
            available=position.available,
            reorder_point=position.reorder_point,
        )
        for position in positions
        if position.site_id != request.destination_site_id
    ]


async def reject(
    session: AsyncSession,
    recommendation: Recommendation,
    *,
    actor: CurrentUser,
    correlation_id: str,
    reason: str,
) -> DecisionOutcome:
    """Refuse a recommendation. A written reason is mandatory."""
    require_decision_authority(actor, AgentName(recommendation.agent))

    if not reason.strip():
        raise DecisionError("A rejection requires a written reason.")
    if recommendation.status != RecommendationStatus.PENDING:
        raise DecisionError(
            f"Recommendation already {recommendation.status}.",
            detail={"status": str(recommendation.status)},
        )

    request = await session.get(ResourceRequest, recommendation.request_id)
    if request is None:
        raise NotFound("Recommendation is attached to an unknown request.")

    before = audit.snapshot(recommendation)
    recommendation.status = RecommendationStatus.REJECTED
    recommendation.decided_by = actor.id
    recommendation.decided_at = now()
    recommendation.decision_reason = reason.strip()
    await session.flush()

    decision_event = await audit.record(
        session,
        action="recommendation.rejected",
        entity_type="recommendation",
        entity_id=recommendation.id,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        before=before,
        after=audit.snapshot(recommendation),
        ai_trace_id=recommendation.agent_run_id,
    )

    await requests_service.transition(
        session,
        request,
        RequestState.REJECTED,
        actor=actor,
        correlation_id=correlation_id,
        note=f"Reason: {reason.strip()}",
        ai_trace_id=recommendation.agent_run_id,
    )

    await activity.add(
        session,
        incident_id=request.incident_id,
        kind=ActivityKind.HUMAN_DECISION,
        body=f"{actor.display_name} REJECTED the recommendation for {request.id}. {reason.strip()}",
        section=IcsSection.LOGISTICS,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        meta={"recommendation_id": recommendation.id, "decision": "rejected"},
        ai_trace_id=recommendation.agent_run_id,
    )

    return DecisionOutcome(
        recommendation=recommendation,
        request=request,
        inventory_audit_events=[],
        decision_audit_event=decision_event,
        moved_total=0,
    )


async def approve(
    session: AsyncSession,
    recommendation: Recommendation,
    *,
    actor: CurrentUser,
    correlation_id: str,
    modified_legs: list[dict[str, Any]] | None = None,
    reason: str = "",
    override_equity: bool = False,
) -> DecisionOutcome:
    """Accept a recommendation, optionally edited, and move the stock.

    ``modified_legs`` replaces the proposed allocation. Supplying it marks the
    decision as ``modified`` rather than ``approved`` so the audit log
    distinguishes "the human agreed" from "the human changed it" — which is
    the distinction that makes a human-in-the-loop claim meaningful.
    """
    require_decision_authority(actor, AgentName(recommendation.agent))

    if recommendation.status != RecommendationStatus.PENDING:
        raise DecisionError(
            f"Recommendation already {recommendation.status}.",
            detail={"status": str(recommendation.status)},
        )

    request = await session.get(ResourceRequest, recommendation.request_id)
    if request is None:
        raise NotFound("Recommendation is attached to an unknown request.")
    if not request.destination_site_id:
        raise DecisionError("Request has no destination site; cannot move stock.")

    was_modified = modified_legs is not None
    legs = (
        _legs_from_payload({"legs": modified_legs})
        if modified_legs is not None
        else _legs_from_payload(recommendation.payload_json or {})
    )
    legs = [leg for leg in legs if leg.quantity > 0]
    if not legs:
        raise DecisionError("An approval must move at least one unit.")

    # Re-run the guardrail against live stock, not the numbers the agent saw.
    candidates = await _current_candidates(session, request)
    review = validate_legs(legs, candidates)

    if not review.passed:
        can_override = has_permission(actor, Permission.DECIDE_ANY)
        if not (override_equity and can_override and reason.strip()):
            raise EquityGuardrailViolation(
                "This allocation breaches the equity floor. Only an Incident Commander "
                "may override it, and a written reason is required.",
                detail={
                    "violations": review.violations,
                    "rule": review.rule_id,
                    "override_allowed": can_override,
                },
            )

    before_recommendation = audit.snapshot(recommendation)
    target_state = RequestState.MODIFIED if was_modified else RequestState.APPROVED

    recommendation.status = (
        RecommendationStatus.MODIFIED if was_modified else RecommendationStatus.APPROVED
    )
    recommendation.decided_by = actor.id
    recommendation.decided_at = now()
    recommendation.decision_reason = reason.strip()
    recommendation.decided_payload_json = {
        "legs": [
            {
                "from_site_id": leg.from_site_id,
                "from_site_name": leg.from_site_name,
                "quantity": leg.quantity,
                "equity_priority": leg.equity_priority,
            }
            for leg in legs
        ],
        "destination_site_id": request.destination_site_id,
        "total": sum(leg.quantity for leg in legs),
        "equity_review": {
            "passed": review.passed,
            "violations": review.violations,
            "overridden": bool(not review.passed),
        },
    }
    await session.flush()

    # The decision row. Written before the movement so that, if a transfer
    # fails, the transaction rolls back both together and the log never claims
    # a decision that produced nothing.
    decision_event = await audit.record(
        session,
        action=f"recommendation.{recommendation.status}",
        entity_type="recommendation",
        entity_id=recommendation.id,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        before=before_recommendation,
        after=audit.snapshot(recommendation),
        ai_trace_id=recommendation.agent_run_id,
    )

    await requests_service.transition(
        session,
        request,
        target_state,
        actor=actor,
        correlation_id=correlation_id,
        note=("Modified before approval." if was_modified else "Approved as recommended."),
        ai_trace_id=recommendation.agent_run_id,
    )

    inventory_events: list[AuditEvent] = []
    for leg in legs:
        event = await inventory.transfer(
            session,
            sku_id=request.sku_id,
            from_site_id=leg.from_site_id,
            to_site_id=request.destination_site_id,
            quantity=leg.quantity,
            actor_id=actor.id,
            actor_label=actor.label,
            correlation_id=correlation_id,
            reason=f"Approved recommendation {recommendation.id} for request {request.id}",
            ai_trace_id=recommendation.agent_run_id,
        )
        inventory_events.append(event)

    moved_total = sum(leg.quantity for leg in legs)
    leg_text = ", ".join(f"{leg.quantity} from {leg.from_site_name}" for leg in legs)
    destination_name = request.destination_site.name if request.destination_site else "destination"
    verb = "MODIFIED and approved" if was_modified else "APPROVED"

    await activity.add(
        session,
        incident_id=request.incident_id,
        kind=ActivityKind.RESOURCE_MOVEMENT,
        body=(
            f"{actor.display_name} {verb} the recommendation for {request.id}: "
            f"{leg_text} -> {destination_name}." + (f" {reason.strip()}" if reason.strip() else "")
        ),
        section=IcsSection.LOGISTICS,
        correlation_id=correlation_id,
        actor_id=actor.id,
        actor_label=actor.label,
        meta={
            "recommendation_id": recommendation.id,
            "decision": str(recommendation.status),
            "moved_total": moved_total,
        },
        ai_trace_id=recommendation.agent_run_id,
    )

    await safe_broadcast(
        request.incident_id,
        "inventory.updated",
        {"request_id": request.id, "moved_total": moved_total},
    )

    return DecisionOutcome(
        recommendation=recommendation,
        request=request,
        inventory_audit_events=inventory_events,
        decision_audit_event=decision_event,
        moved_total=moved_total,
    )
