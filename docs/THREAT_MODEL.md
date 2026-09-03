# Threat model

Short by design. The purpose is to be explicit about two different things: why
this repository is safe to be public, and what would have to change before
anything like it went near a real operation.

## Why this repository is safe to publish

**There is nothing here to protect.**

Every fixture is invented — not anonymised, not de-identified. No real incident,
no real people, no real places, no patient or victim records, no agency
hostnames, no production endpoints, no credentials. The SOP corpus in
`knowledge/` was written for this demo and says so on every page.
[ADR-0006](adr/0006-synthetic-data-only-public-release.md) records why the strong
claim was chosen over "carefully sanitised real data": the strong claim is
checkable by reading `fixtures/`, and the weak one asks for trust the reader has
no basis to extend.

**The demo passwords are published on purpose.** `ic.demo`, `ops.demo`, and
`logistics.demo` all use `demo`. This is safe only because the accounts are
fictional and the deployment is local. See `SECURITY.md`.

**Nothing calls out by default.** With `LLM_PROVIDER=none` — the default — the
application makes no outbound network request at all.

## Demo threats (in scope)

| Threat | Mitigation |
|---|---|
| A screenshot is mistaken for a real EOC | Non-dismissible `SYNTHETIC DEMO` banner in the root layout; incident name ends `-REF`; `robots: noindex` |
| A reviewer reuses the demo password somewhere real | Stated in README, `SECURITY.md`, and the fixture files |
| Someone deploys this as-is | `DEMO_MODE` gates seeded operators and the operator-enumeration endpoint; ports and defaults are local-only |
| Path traversal through the knowledge endpoint | Filename-only, `.md` required, resolved parent must equal the knowledge directory; covered by a test |
| Unauthenticated writes | Every mutating endpoint depends on `current_user`; covered by a test asserting 401 across all six |
| Privilege escalation between ICS roles | Authority table in `app/security.py`, enforced server-side; the UI mirrors it only to decide what to render |
| Corrupted or edited history | Hash-chained audit log with `GET /api/audit/verify` |
| An AI output moving stock | No import path from `app/agents/*` to `app/inventory` |

## Deliberate weaknesses (demo-only, and their production replacements)

These are real weaknesses. They are listed so nobody has to discover them, and
each one is a conscious trade for runnability.

**1. The bearer token lives in `localStorage`.**
It is therefore exposed to XSS. Chosen because the web app and API run on
different origins in the default local setup, and a cross-origin cookie needs
`SameSite=None; Secure`, which does not work over plain HTTP on localhost — a
demo that requires TLS to log in is a demo nobody runs.
*Production:* same-origin deployment with an `httpOnly`, `Secure`, `SameSite=Lax`
cookie and CSRF protection.

**2. The WebSocket token is a query parameter.**
Query strings land in access logs and proxy logs. The browser WebSocket API
cannot set headers, so there is no clean alternative at this size.
*Production:* exchange a short-lived, single-use ticket over HTTP and present
that on the socket.

**3. Demo authentication has no real controls.**
No identity provider, no MFA, no lockout, no rate limiting, no password policy,
no session revocation. Tokens are signed with a per-process secret when
`DEMO_JWT_SECRET` is blank, so they do not even survive a restart.
*Production:* the agency IdP, SAML or OIDC, MFA, and short sessions.

**4. The audit log is tamper-*evident*, not tamper-*proof*.**
This distinction is the most important line in this document. The hash chain
detects careless or partial edits — change one historical row and
`/api/audit/verify` names the sequence number that broke. It does **not** stop an
attacker with database write access, who can simply recompute the chain from the
point they altered. The chain never leaves the trust boundary it is protecting.
*Production:* write digests to an append-only external store (object lock / WORM),
sign them, and publish periodic digests somewhere the operator cannot rewrite.

**5. Single-process assumptions.**
The WebSocket hub is in-process and audit chain appends are serialised with an
`asyncio.Lock`. A second replica would break fan-out and could fork the chain.
*Production:* Redis pub/sub for fan-out, and a database sequence or a single
designated writer for the chain.

**6. No transport security, no secrets management.**
Plain HTTP on localhost, secrets read from `.env`.
*Production:* TLS everywhere, a managed secret store, rotation.

**7. `demo-operators` enumerates accounts.**
Guarded by `DEMO_MODE` and harmless for fictional accounts; it would be an
information-disclosure bug anywhere else.

## Production threats this slice does not address

Named so their absence is not mistaken for completeness.

- **Tenant isolation.** Single-tenant by construction.
- **Availability.** No HA, no failover, no backups, no DR. An EOC tool that is
  down during an incident is worse than useless; this one makes no availability
  claim at all.
- **Supply chain.** Dependencies are pinned by lockfile and CI runs on push, but
  there is no SBOM, no signing, no provenance attestation.
- **Prompt injection.** Real when a model is enabled. The corpus is trusted and
  static, and no agent has a tool that writes, so the blast radius here is
  limited to misleading advisory text. A production system ingesting external
  documents needs input isolation and output validation.
- **Insider threat.** No separation of duties beyond ICS roles, no four-eyes
  requirement on high-value movements, no anomaly detection.
- **Data retention and legal hold.** Nothing expires, nothing is exportable in an
  evidentiary format.

## If you find a problem

See `SECURITY.md`. Since this repository contains no real data and no production
system, findings here are software defects rather than incidents — but a
credential-shaped string or anything resembling real data appearing in this repo
*would* be a genuine finding, and is worth reporting privately.
