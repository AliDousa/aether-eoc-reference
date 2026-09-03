# Contributing

Thanks for looking. Please read this first — it will save you time, because this
repository declines a category of contribution that most repositories welcome.

## What this repository is

A **reference slice**: a deliberately narrow, fully working demonstration of how
a public-health Emergency Operations Centre could work, built to be read and run
in about twenty minutes. It is a portfolio and teaching artefact, not a product
and not a deployment.

Its value is inversely proportional to its surface area. Every feature added is
one more thing a reviewer has to read past to find the argument.

## Contributions that will be declined

Not because they are bad ideas — several are things a real system needs — but
because they defeat the purpose of this repository.

**Production integrations.** FHIR, health information exchanges, national or
agency APIs, port and supply-chain feeds, notification gateways, GIS tile
providers. The entire premise of a *sanitised* reference slice is that it has
none. See [ADR-0006](docs/adr/0006-synthetic-data-only-public-release.md).

**Real authentication.** SAML, OIDC, an agency identity provider. The demo auth
is deliberately trivial and deliberately documented as inadequate in
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

**Autonomous execution.** Any path that lets an agent commit resources without a
human decision — including "with a rollback window", including behind a feature
flag. This is the one thing the repository exists to argue against.
[ADR-0005](docs/adr/0005-supervisor-specialist-agents-with-hitl.md).

**Real or "anonymised" data.** Fixtures are invented, not de-identified. A PR
containing anything traceable to a real incident, person, place, or agency will
be closed without merge.

**A seventh module.** Multi-tenancy, billing, a board designer, a workflow
builder, a mobile app, Kubernetes manifests. If it does not serve the
twenty-minute review, it does not belong here.

**Agent frameworks.** The supervisor is a ~250-line module on purpose. A
framework would add a dependency and vocabulary in exchange for replacing a
switch statement.

## Contributions that are very welcome

- **Bugs.** Anything that does not work as documented, especially in the demo
  script.
- **Wrong documentation.** Any place the docs describe behaviour the code does
  not have. Documentation drift is the fastest way for a reference repo to stop
  being one.
- **Accessibility.** Keyboard traps, contrast failures, missing labels, anything
  that conveys state by colour alone. That last one is a hard rule here.
- **Clarity.** A module that would be easier to follow with a better name, a
  clearer boundary, or a comment explaining *why*.
- **Correctness of the domain model.** If the ICS structure, the request
  lifecycle, or the equity reasoning is wrong or misleading, that is worth
  fixing — this is a domain where being plausibly wrong is worse than being
  obviously incomplete.
- **Tests** that pin down existing guarantees.
- **Portability.** Something that breaks on a platform I did not test.

If you are unsure, open an issue before writing code.

## Working on it

```bash
make install
make seed
make dev

make test        # 18 API + 10 web, no API key required
make lint        # ruff + eslint
make typecheck   # pyright + tsc
make fmt         # ruff format + prettier
```

CI runs lint, typecheck, and tests on every push and pull request, with no
secrets available. If your change needs a key to pass, it is out of scope by
definition.

## Standards

- **Python** is typed, with Pydantic models on every HTTP boundary. Ruff and
  Pyright must be clean.
- **TypeScript** is strict. `any` requires a comment explaining why; there are
  currently none.
- **Functions that change state** take an `actor_id` and a `correlation_id`.
  This is what makes the audit log readable as a story.
- **Comments explain *why*, not *what*.** The code already says what it does.
- **Two structural rules that must not be broken:**
  1. `app.inventory` is the only module that mutates stock, and it always writes
     the matching audit row in the same transaction.
  2. Nothing under `app/agents/` may import `app.inventory`. The guardrail is
     enforced by the import graph, and a PR that breaks it will be rejected even
     if every test passes.
- **Commits** are meaningful and scoped: `feat: seed heat-surge fixture`,
  `fix: equity floor re-checked at execution time`, `docs: adr 0005 agents`.

## Reporting security issues

See [`SECURITY.md`](SECURITY.md). Please do not open a public issue for anything
that looks like real data appearing in this repository — that would be a genuine
finding, and I would want to know privately.
