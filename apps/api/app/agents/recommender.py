"""Resource Recommender.

Proposes how to fill a resource request from available stock. It never writes
inventory — it returns a plan, and only ``app.inventory.transfer``, called from
a human decision, moves anything.

The allocation rules are transcribed from
``knowledge/resource-allocation-equity-rules.md`` so that a reviewer can check
the code against a written standard rather than against the author's taste:

* §1 precedence: Immediate > Priority > Routine.
* §3 equity floor (hard): never reduce a site with equity priority 4-5 to zero
  in order to serve a lower-priority site. Fails closed.
* §4 draw order: reserve/staging (1-2) first, then baseline (3) down to its
  reorder point, then high-need (4-5) only while staying strictly above zero
  and above 25 % of reorder point.
* §4 also: prefer fewer legs, because transport is the scarce resource.

The planner is a pure function over :class:`Candidate` values so it can be
tested without a database or a model.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from app import rag
from app.agents.base import AgentResult
from app.enums import AgentName, AgentRunStatus, Priority

# The rule this module implements, cited in every equity review it produces.
EQUITY_RULE_ID = "resource-allocation-equity-rules.md#3-the-equity-floor-hard-constraint"
DRAW_ORDER_RULE_ID = "resource-allocation-equity-rules.md#4-multi-site-allocation"

# Sites at or above this equity priority are protected by the floor in §3.
HIGH_EQUITY_THRESHOLD = 4


@dataclass(frozen=True)
class Candidate:
    """A potential source site for one SKU."""

    site_id: str
    site_name: str
    equity_priority: int
    available: int
    reorder_point: int

    @property
    def is_high_equity(self) -> bool:
        return self.equity_priority >= HIGH_EQUITY_THRESHOLD

    @property
    def reserve_floor(self) -> int:
        """Stock this site must retain after any movement.

        Reserve and staging sites (1-2) may be drawn to zero: holding stock for
        others is their function. Baseline sites (3) keep their reorder point.
        High-need sites (4-5) keep the larger of one unit and a quarter of
        their reorder point — they may never reach zero.
        """
        if self.equity_priority <= 2:
            return 0
        if self.equity_priority == 3:
            return self.reorder_point
        return max(1, math.ceil(0.25 * self.reorder_point))

    @property
    def max_draw(self) -> int:
        return max(0, self.available - self.reserve_floor)

    @property
    def tier(self) -> int:
        """Draw order per §4. Lower is drawn first."""
        if self.equity_priority <= 2:
            return 1
        if self.equity_priority == 3:
            return 2
        return 3


@dataclass
class Leg:
    """One movement in a plan: take ``quantity`` from one site."""

    from_site_id: str
    from_site_name: str
    quantity: int
    equity_priority: int
    available_before: int
    available_after: int


@dataclass
class EquityReview:
    """The guardrail verdict. Always attached to a plan, pass or fail."""

    passed: bool
    rule_id: str = EQUITY_RULE_ID
    summary: str = ""
    considered: list[dict[str, Any]] = field(default_factory=list)
    withheld: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AllocationPlan:
    requested: int
    allocated: int
    shortfall: int
    legs: list[Leg]
    equity: EquityReview
    notes: list[str] = field(default_factory=list)

    @property
    def fully_filled(self) -> bool:
        return self.shortfall == 0

    def as_payload(self, *, destination_site_id: str | None, sku_code: str) -> dict[str, Any]:
        return {
            "sku_code": sku_code,
            "destination_site_id": destination_site_id,
            "requested_quantity": self.requested,
            "allocated_quantity": self.allocated,
            "shortfall": self.shortfall,
            "fully_filled": self.fully_filled,
            "legs": [asdict(leg) for leg in self.legs],
            "notes": self.notes,
        }


def plan_allocation(
    *,
    requested: int,
    candidates: list[Candidate],
    priority: Priority,
    destination_equity: int | None = None,
) -> AllocationPlan:
    """Build an allocation plan that respects the equity floor.

    Fails closed: a leg that would breach §3 is never emitted. When the only
    remaining stock sits behind the floor, the plan returns a shortfall and
    records what was withheld and why, rather than quietly taking it.
    """
    ordered = sorted(candidates, key=lambda c: (c.tier, c.equity_priority, -c.available))

    legs: list[Leg] = []
    considered: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    remaining = max(0, requested)

    for candidate in ordered:
        drawable = min(candidate.max_draw, remaining)
        record: dict[str, Any] = {
            "site_id": candidate.site_id,
            "site_name": candidate.site_name,
            "equity_priority": candidate.equity_priority,
            "available": candidate.available,
            "reserve_floor": candidate.reserve_floor,
            "max_draw": candidate.max_draw,
            "drawn": drawable if remaining > 0 else 0,
        }
        considered.append(record)

        # Record protected stock even when we did not need it, so the review
        # shows the floor was applied rather than coincidentally unbreached.
        if candidate.available > candidate.max_draw:
            withheld.append(
                {
                    "site_id": candidate.site_id,
                    "site_name": candidate.site_name,
                    "equity_priority": candidate.equity_priority,
                    "retained": candidate.available - candidate.max_draw,
                    "reason": (
                        f"Equity priority {candidate.equity_priority} site retains "
                        f"{candidate.available - candidate.max_draw} unit(s) "
                        "under the equity floor."
                        if candidate.is_high_equity
                        else f"Baseline site held at its reorder point ({candidate.reorder_point})."
                    ),
                }
            )

        if remaining <= 0 or drawable <= 0:
            continue

        legs.append(
            Leg(
                from_site_id=candidate.site_id,
                from_site_name=candidate.site_name,
                quantity=drawable,
                equity_priority=candidate.equity_priority,
                available_before=candidate.available,
                available_after=candidate.available - drawable,
            )
        )
        remaining -= drawable

    allocated = sum(leg.quantity for leg in legs)
    shortfall = max(0, requested - allocated)

    notes: list[str] = []
    if shortfall:
        notes.append(
            f"Shortfall of {shortfall} unit(s). The equity floor prevents drawing further "
            "from high-need sites. Options: partial fill as planned, Incident Commander "
            "override with a recorded reason, or external resupply."
        )
    if len(legs) > 1:
        notes.append(
            f"Multi-site allocation across {len(legs)} sites; each leg is a separate "
            "transport task."
        )
    if priority is Priority.IMMEDIATE and shortfall:
        notes.append("IMMEDIATE priority with an unfilled balance — escalate to the IC.")
    if destination_equity is not None and destination_equity >= HIGH_EQUITY_THRESHOLD:
        notes.append(f"Destination is an equity priority {destination_equity} site (high need).")

    equity = EquityReview(
        passed=True,
        summary=(
            "Equity floor satisfied: no high-need site is reduced to zero."
            if not shortfall
            else "Equity floor satisfied, but it caps the fill. Shortfall reported rather "
            "than drawn from protected stock."
        ),
        considered=considered,
        withheld=withheld,
    )

    return AllocationPlan(
        requested=requested,
        allocated=allocated,
        shortfall=shortfall,
        legs=legs,
        equity=equity,
        notes=notes,
    )


def validate_legs(legs: list[Leg], candidates: list[Candidate]) -> EquityReview:
    """Re-check an allocation against the equity floor at execution time.

    A human may edit a plan before approving it. The floor is enforced again
    here so that the guardrail lives on the execution path, not only in the
    proposal — an edited plan gets the same scrutiny as a generated one.
    """
    by_id = {c.site_id: c for c in candidates}
    violations: list[dict[str, Any]] = []

    for leg in legs:
        candidate = by_id.get(leg.from_site_id)
        if candidate is None:
            violations.append(
                {"site_id": leg.from_site_id, "reason": "Unknown source site for this SKU."}
            )
            continue
        if leg.quantity > candidate.available:
            violations.append(
                {
                    "site_id": candidate.site_id,
                    "site_name": candidate.site_name,
                    "reason": (
                        f"Requested {leg.quantity} exceeds available {candidate.available}."
                    ),
                }
            )
            continue
        remaining_after = candidate.available - leg.quantity
        if candidate.is_high_equity and remaining_after < candidate.reserve_floor:
            violations.append(
                {
                    "site_id": candidate.site_id,
                    "site_name": candidate.site_name,
                    "equity_priority": candidate.equity_priority,
                    "reason": (
                        f"Would leave {remaining_after} at an equity priority "
                        f"{candidate.equity_priority} site; the floor requires at least "
                        f"{candidate.reserve_floor}."
                    ),
                }
            )

    return EquityReview(
        passed=not violations,
        summary=(
            "Equity floor satisfied."
            if not violations
            else "Equity floor breached by the edited allocation."
        ),
        violations=violations,
    )


async def run(
    *,
    sku_code: str,
    sku_name: str,
    requested: int,
    priority: Priority,
    candidates: list[Candidate],
    destination_site_id: str | None,
    destination_site_name: str | None,
    destination_equity: int | None,
) -> AgentResult:
    """Produce a recommendation for one request.

    Deterministic. No model is consulted even when one is configured: an
    allocation is arithmetic against a written rule, and a language model would
    add variance without adding correctness. The model path exists for the
    narrative agents, where prose quality is the value.
    """
    plan = plan_allocation(
        requested=requested,
        candidates=candidates,
        priority=priority,
        destination_equity=destination_equity,
    )

    hits = rag.search(
        f"allocation equity floor multi-site draw order {priority.value} priority", limit=3
    )
    citations = [hit.as_citation() for hit in hits]
    # The rule this agent implements is always cited, even if BM25 ranked
    # another section higher — the reader should be able to check the floor.
    if EQUITY_RULE_ID not in [c["id"] for c in citations]:
        rule_chunk = rag.resolve_citation(EQUITY_RULE_ID)
        if rule_chunk:
            citations.insert(
                0,
                {
                    "id": rule_chunk.id,
                    "source": rule_chunk.source,
                    "title": rule_chunk.title,
                    "anchor": rule_chunk.anchor,
                    "preview": rule_chunk.preview,
                    "score": 0.0,
                },
            )

    destination = destination_site_name or "the requesting site"
    if plan.legs:
        leg_text = ", ".join(f"{leg.quantity} from {leg.from_site_name}" for leg in plan.legs)
        headline = (
            f"Allocate {plan.allocated} of {plan.requested} {sku_name} to {destination}: "
            f"{leg_text}."
        )
    else:
        headline = (
            f"No allocation possible for {plan.requested} {sku_name} to {destination} "
            "without breaching the equity floor."
        )

    summary_lines = [headline]
    if plan.shortfall:
        summary_lines.append(f"Shortfall: {plan.shortfall} {sku_name} remain unfilled.")
    summary_lines.extend(plan.notes)
    summary_lines.append("This is advice. No stock moves until a human approves it.")

    uncertainty: list[str] = []
    if plan.shortfall:
        uncertainty.append("Resupply timing for the unfilled balance is unknown to this system.")
    uncertainty.append(
        "Stock figures are as recorded in the board; physical counts are not verified here."
    )
    if len(plan.legs) > 1:
        uncertainty.append("Transport capacity for multiple legs is not modelled.")

    confidence = 0.86 if plan.fully_filled else 0.62

    return AgentResult(
        agent=AgentName.RESOURCE_RECOMMENDER,
        intent="resource_recommendation",
        summary="\n".join(summary_lines),
        structured=plan.as_payload(destination_site_id=destination_site_id, sku_code=sku_code)
        | {"equity_review": asdict(plan.equity)},
        citations=citations,
        confidence=confidence,
        uncertainty=uncertainty,
        mode="fixture",
        model_id="deterministic-rules-v1",
        raw_output="\n".join(summary_lines),
        # Always. Allocating stock is exactly the class of output that must not
        # execute on its own.
        requires_human=True,
        status=AgentRunStatus.AWAITING_HUMAN,
    )
