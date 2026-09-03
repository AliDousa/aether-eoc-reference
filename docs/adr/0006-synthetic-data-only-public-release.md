# ADR-0006: Synthetic data only, and what that costs

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

The author works on public-health emergency systems. The production platforms
behind that work handle live incident data, health-system integrations, and
information whose disclosure would be harmful — and which is not the author's to
publish regardless.

A public portfolio repository in this domain therefore has a sharp constraint.
The temptation is to "sanitise" real material: take a real incident, rename the
hospitals, round the casualty figures, keep the structure. That is a bad idea
for three separate reasons:

1. Sanitisation reliably fails. Structure, timing, and ratios re-identify.
2. Even successful sanitisation makes an implicit claim about a real event.
3. A reader cannot tell sanitised material from invented material, so every
   claim in the repository inherits the doubt.

## Decision

**Everything in this repository is invented.** Not anonymised, not
de-identified, not derived from a real incident — invented, for this demo.

Concretely:

- One fictional incident, `HEAT-2026-DUBAI-REF`, describing no real event.
- Operators are role-shaped labels: `IC-Demo`, `LOGISTICS-1`, `Operator North`.
  There are no invented humans with plausible names.
- Sites are generic sectors. Coordinates are a regularly-spaced artificial grid
  — obviously synthetic on inspection — and are placeholders for a map this
  slice does not ship.
- The SOP corpus in `knowledge/` was **written for this repository**. Every file
  opens with `DEMO PROTOCOL — not official guidance.`
- Every data file carries a `SYNTHETIC FIXTURE — not operational data` banner.
- No patient records, no victim lists, no casualty counts presented as real, no
  agency hostnames, no production endpoints, no credentials.
- The demo passwords are published in the README, which is only safe because
  every account is fictional.

Enforced by a sanitisation sweep before the first public commit, and by the
`SYNTHETIC DEMO` banner rendered on every page of the UI.

## Rationale

- **The strong claim is easier to verify than the weak one.** "Nothing here is
  real" can be checked by reading `fixtures/` and `knowledge/`. "This was
  carefully anonymised" cannot be checked at all, and asks the reader for trust
  they have no basis to extend.
- **Invented data is better demo data.** Real incidents are messy in ways that
  obscure the thing being demonstrated. The ORS contention here is *designed* so
  that no single site can fill the request and the equity floor caps the rest —
  a scenario that exercises exactly the guardrail worth showing. Real data would
  not have obliged.
- **A screenshot has no context.** Someone will screenshot this tool. The banner
  is not dismissible and the incident name ends in `-REF` so that an image taken
  out of context still says what it is.
- **Role-shaped names are the correct default anyway.** They are what the
  redactor produces before any model call, so the fixtures and the outbound
  redaction agree.

## Alternatives considered

**Anonymised real data.** Rejected; see above. This is the decision this ADR
exists to record.

**A blank application with no seed data.** Rejected. The reviewer would meet
empty states, which demonstrate nothing, and the twenty-minute review would
become a data-entry exercise. Empty states are explicitly a non-goal on first
load.

**Public open datasets.** Considered, and rejected as unnecessary complexity: a
real open dataset would still need reshaping into ICS resource requests, and
would import licensing and provenance questions for no gain over invented data.

**Keeping the repository private.** Defeats its purpose. The point is that the
inspectable parts *are* inspectable.

## Consequences

**Accepted:**

- The scenario is tidier than reality. Real incidents have contradictory
  reports, missing data, and requests that never get resolved. Some of this is
  reflected — the rejected field-epidemiology request, the mandatory
  information-gaps section, the unfilled shortfall — but the demo is legible in
  a way real operations are not.
- The equity rules are the author's synthesis for demonstration, not any
  jurisdiction's actual policy. Labelled as such in the corpus itself.
- No performance or scale evidence: forty inventory rows proves nothing about
  forty thousand.

**Gained:**

- The repository can be public without review, redaction, or risk.
- Every claim is checkable, because the reader can see the whole input.
- The demo is deterministic and reproducible: `make reset` returns to a known
  state, which is also what makes the count-based tests meaningful.

## Implementation notes

- `fixtures/README.md` carries the literal `# SYNTHETIC FIXTURE` banner. JSON has
  no comment syntax, so the `.json` files carry it as a `_notice` key instead —
  the same statement, in the only form the format allows.
- The seeder replays `fixtures/timeline.json` through the real service
  functions, so seeded history could not have been produced by anything the
  application cannot itself do.
- The sanitisation sweep greps for emails, phone numbers, private IPs, API-token
  shapes, `.env`, `id_rsa`, agency names, `NABIDH`, hospital names, and
  production connection strings. It is documented in `docs/THREAT_MODEL.md` and
  was run before the first commit to `main`.
- The UI banner lives in `apps/web/components/demo-banner.tsx` and is rendered
  by the root layout, so it cannot be omitted from a page by accident.
