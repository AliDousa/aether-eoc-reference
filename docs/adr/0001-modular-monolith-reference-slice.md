# ADR-0001: A modular monolith, delivered as a reference slice

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

The subject matter — an emergency operations centre — invites an architecture
diagram with a dozen services on it. Real EOC platforms do accumulate that
shape: ingestion workers, a notification tier, a GIS service, a reporting
warehouse, an integration bus.

But the audience for *this* repository is a technical reviewer with twenty
minutes and no prior context. Their question is not "can this scale to a
national deployment"; it is "does this person understand the problem, and can
they build something that holds together". A distributed system answers the
first question and obscures the second.

There is also a scope pressure specific to reference implementations: every
service boundary is a place to put a stub. Stubs make an architecture look
complete while making the product hollow, which is the opposite of what a
portfolio artefact should do.

## Decision

Build a **modular monolith** with exactly two deployable processes:

1. `apps/api` — FastAPI. REST, WebSocket, the agent supervisor, and persistence.
2. `apps/web` — Next.js. The operator UI.

Module boundaries are enforced by convention and by dependency direction inside
the Python package, not by network hops. In particular:

- `app.inventory` is the only module that mutates stock.
- `app.audit` is the only module that writes the audit log.
- `app.agents.*` may read anything and write nothing.

## Rationale

- **Readability is the deliverable.** A reviewer can follow the entire
  approve-a-recommendation path — HTTP handler, authority check, equity
  re-validation, stock movement, audit write, WebSocket broadcast — by reading
  four files in one sitting.
- **The guardrail is structural.** "The AI cannot move inventory" is true here
  because there is no code path from `app.agents` to `app.inventory`. That is
  checkable by grep. Across a service boundary it would be a policy claim about
  a network call.
- **Two processes is the honest minimum.** The UI is a separate runtime because
  it genuinely is; nothing else here is.

## Alternatives considered

**Microservices (incident service, resource service, agent service).**
Rejected. It would triple the operational surface, add failure modes the demo
cannot exercise, and force either a shared database (defeating the point) or
distributed transactions across the one path that must be atomic — the decision
plus the stock movement plus the audit row.

**A single Next.js application with route handlers, no Python.**
Tempting for simplicity, and rejected on domain grounds. The epidemiological and
analytical half of this problem space lives in Python, and the sibling repo
[`phim`](https://github.com/AliDousa/phim) is Python. A TypeScript-only EOC would
misrepresent how these systems actually get built.

**Serverless functions.** Rejected: the WebSocket hub is in-process state, and
introducing a fan-out tier to work around a deployment choice would be tail
wagging dog for a demo.

## Consequences

**Accepted:**

- The in-process WebSocket hub means a second API replica would not share
  presence or broadcasts. Documented in ADR-0003 rather than solved.
- The audit hash chain is serialised by an `asyncio.Lock`, which is correct for
  one process and insufficient for several. Documented in ADR-0004.
- Scaling past a single node needs real work. That work is deliberately not
  done, because doing it badly would be worse than not doing it.

**Gained:**

- `git clone && make install && make seed && make dev` is the whole setup.
- The test suite runs against the real service functions with no test doubles
  for the domain logic.
- The seeder replays its scripted history through the same code the application
  uses, so the demo data cannot drift from application behaviour.

## Implementation notes

- Python is managed with **uv** — one runner, one lockfile, no ambiguity about
  whether to use pip, Poetry, or a virtualenv by hand.
- The JavaScript package manager is **npm** rather than pnpm. npm ships with
  Node, so a reviewer needs no extra install; for a single-package app there is
  no pnpm benefit worth that friction.
- `@tanstack/react-table` was in the intended stack and was **removed**. Version
  9 is a rewrite whose previous API now sits behind a `./legacy` export. These
  are dense operational tables with no virtualisation, grouping, or column
  resizing; a plain semantic `<table>` is clearer to read, has no API-churn
  risk, and avoids shipping a dependency in compatibility mode. TanStack Query
  is still used, and does real work.
- `@hookform/resolvers` was **removed** and replaced by a twenty-line resolver
  in `apps/web/lib/form.ts`. It requires `ajv@^8` while ESLint 9 requires
  `ajv@^6`; npm writes a lockfile for that pair which it then rejects under
  `npm ci` (reproducible from a clean tree on both npm 10 and 11), so CI could
  not install strictly. The alternatives were to weaken CI to `npm install` or
  to carry a dependency tree for a single form. React Hook Form's resolver
  contract is one function — take values, return values or field errors — so
  owning it was the smaller cost. It is covered by `apps/web/tests/form.test.ts`,
  because first-party code should be tested rather than trusted.
