# Product notes

> **Synthetic demonstration.** Nothing in this repository is real. See
> [ADR-0006](adr/0006-synthetic-data-only-public-release.md).

## The problem

An Emergency Operations Centre coordinates a response that nobody can see all of
at once. During a public-health surge — a heat dome over a mass gathering, an
outbreak, a mass-casualty event — a duty floor of ten to forty people has to
maintain one shared picture of what is happening, what has been asked for, what
has been committed, and what is about to run out.

The software most agencies use for this is a decade or two old. The complaints
are consistent across jurisdictions:

**Collaboration is not really shared.** Boards are forms over a database.
Someone edits a record; everyone else finds out when they next refresh, or when
somebody says so out loud. Two sections act on different versions of the same
resource picture, and the divergence is discovered afterwards.

**Workflow is rigid but not enforced.** Boards are configurable in the sense that
an administrator can add fields. They are rigid in the sense that the actual
lifecycle of a resource request — who may approve what, in which order, under
what constraint — is implied by conventions and training rather than expressed
in the system. So it is both hard to change *and* routinely bypassed.

**The audit trail answers the wrong question.** Most systems record that a row
changed and who was logged in. Very few record *why*, what the alternatives
were, or what information the decision was made on. That is precisely what a
post-incident review needs.

**AI is arriving without guardrails.** The current wave of "AI for emergency
management" is pitched as autonomy — the system spots a shortage and moves the
resources. In a domain where resource decisions carry legal authority,
professional accountability, and equity consequences, an unexplainable
allocation is one nobody can defend. The interesting question is not whether a
model can propose an allocation. It is whether the proposal, the reasoning, the
human decision, and the resulting movement are all on the record as separate,
linked facts.

## Who this is for

ICS roles, and what each of them needs from this slice:

| Role | Needs | In this slice |
|---|---|---|
| **Incident Commander** | The decisions waiting on their authority, and what is about to fail | Board KPIs, pending AI reviews, authority to approve anything, sole authority to override the equity floor |
| **Operations Section** | To log what is happening and raise needs | Posts to the activity stream, raises requests, runs advisory agents. **Cannot** commit resources |
| **Logistics Section** | Source sites, stock levels, what needs tasking | Request queue ordered by urgency, allocation proposals, authority to decide logistics recommendations |
| **Planning Section** | The situation picture and its gaps | Situation Assessment agent with a mandatory information-gaps section |
| **Finance / Admin** | Cost capture | **Not implemented.** Shown on the board as present-but-unimplemented rather than silently omitted |

## What this slice does

Three verticals, chosen because together they demonstrate the whole argument and
separately they each stand up.

### A. Live incident board

One active incident. ICS section chips, an operational-period clock, KPIs that
each have an owner and an action behind them, an append-only activity stream,
and presence showing who is on the board.

Posting a log note is optimistic — it appears immediately, marked unconfirmed —
but the server stays the source of truth: the optimistic row is visually
distinct and is replaced by the server's copy, or removed with the text handed
back if the write fails.

The role toggle changes *emphasis*, not data. Everyone sees every request;
column order and highlighting follow the role. Hiding rows from an operator on a
shared board causes more problems than it solves.

### B. Resource requests, with real contention

A catalogue of fictional resources and a request lifecycle:

```
draft → submitted → recommended → approved | modified | rejected → tasked → fulfilled
```

with `cancelled` reachable from any non-terminal state. The legal transitions
live in one table (`app/state_machine.py`) and the API returns the permitted
next moves with every request, so the UI renders the server's rules instead of
duplicating them.

The seeded scenario is built around a genuine shortage. An IMMEDIATE request for
400 ORS kits cannot be filled from any single site, and the equity floor caps
what may be taken from the one remaining cooling centre. The correct answer is a
multi-site allocation *with a stated shortfall* — not a clean fill.

### C. AI orchestration that stops

A supervisor routes an intent to one of three narrow specialists. Two are
advisory. The third proposes allocations and **cannot execute them**: no agent
module imports the inventory service, so the guardrail is structural rather than
procedural.

The equity check is the part worth reading. Transcribed from
`knowledge/resource-allocation-equity-rules.md`, it fails closed: when the only
way to fill a request is to zero out a high-need site, the system reports a
shortfall instead of taking the stock. Only an Incident Commander may override
that, and only with a written reason, which is recorded.

## What this slice is not

Explicit non-goals. Each of these was considered and cut.

- **Not a product.** No multi-tenancy, no billing, no administration, no
  configuration UI, no board designer.
- **No real integrations.** No FHIR, no health-information-exchange adapters, no
  port or supply-chain feeds, no agency identity provider. The absence is the
  point: this is the half that is safe to inspect.
- **No autonomous execution.** Ever. See ADR-0005.
- **No GIS.** Sites carry coordinates and no map is drawn. A map needing a paid
  tile key would make the demo unrunnable, and an offline map would add a module
  without adding to the argument.
- **Not multi-incident.** One incident, deliberately. Incident routing is a
  product feature, not an architectural insight.
- **No mobile app.** The UI is responsive enough to review on a phone.
- **Not a clinical tool.** The corpus in `knowledge/` is invented for this demo
  and says so on every page.

## How it relates to `phim`

[`phim`](https://github.com/AliDousa/phim) is the modelling half: epidemiological
forecasting, SEIR and agent-based models, calibration. It answers *what is
likely to happen*.

This repository is the operations half. It answers *what are we doing about it,
who decided, and on what basis*. The two are complementary and deliberately
separate — a forecast is an input to an incident action plan, not a substitute
for one, and the failure mode of merging them is a system that presents a model
output as a decision.

Neither repository contains production code. Production platforms stay private.
