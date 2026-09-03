> **DEMO PROTOCOL — not official guidance. For software demonstration only.**
>
> This document is synthetic. It encodes the allocation rules that the demo's
> Resource Recommender agent is required to respect, so that a reviewer can
> check the agent's output against a written standard. It has no real-world
> authority.

# Resource Allocation and Equity Rules

Owning section: Logistics, with Incident Commander oversight.
Applies to: all resource requests raised against an active incident.

## 1. Precedence order

Requests are served in this order:

1. **Immediate** — life-safety within the current operational period.
2. **Priority** — degradation of care or capability within 24 hours.
3. **Routine** — replenishment and sustainment.

Precedence never overrides the equity floor in section 3.

## 2. Site equity priority

Every site carries an **equity priority** from 1 to 5, set during planning and
reviewed each operational period.

| Priority | Meaning |
|----------|---------|
| 5 | Highest need. Underserved population, limited alternatives, or no nearby substitute site. |
| 4 | Elevated need. |
| 3 | Baseline. |
| 2 | Lower need, or holds reserve stock for others. |
| 1 | Lowest need. Typically a staging or transit location. |

Equity priority describes the **population served**, not the importance of the
staff there. A warehouse is a 2 not because it matters less, but because
nobody depends on it directly for care.

## 3. The equity floor (hard constraint)

> An allocation must not reduce the available stock of a site with equity
> priority 4 or 5 to **zero** in order to serve a site with a lower equity
> priority.

This is a *fail-closed* rule. If the only way to fill a request is to zero out
a higher-need site, the allocation is **not** proposed. The request is instead
returned to the requester with a shortfall note, and the options are:

- Partial fill from lower-priority sites, with the shortfall stated explicitly.
- Escalation to the Incident Commander for an override, recorded with a reason.
- External resupply request.

An automated system may **never** apply the override itself. Only a human with
Incident Commander authority may accept an allocation that breaches the equity
floor, and the reason must be recorded.

## 4. Multi-site allocation

When no single site can fill a request, draw from multiple sites in this order:

1. Sites with equity priority **1–2** (reserve and staging), lowest first.
2. Sites with equity priority **3**, provided they remain above their reorder point.
3. Sites with equity priority **4–5** only if they remain **strictly above zero**
   and above 25 % of their reorder point after the movement.

Prefer fewer legs over marginally better balance: each additional source site
adds a transport task, and transport is the scarce resource during a surge.

## 5. Reorder points

A site below its reorder point is flagged on the board but is **not**
automatically resupplied. Reorder is a Logistics decision, because during a
surge the reorder point is frequently the wrong target.

## 6. What an automated recommender must always do

- State the shortfall explicitly when one exists. Never round a shortfall away.
- Show the equity check result, including which sites were considered and
  rejected.
- Cite the rule that produced the outcome.
- Stop before execution. A recommendation is advice; only a human commits
  stock.
