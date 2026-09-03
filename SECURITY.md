# Security policy

## What this repository is

A synthetic demonstration. It contains no real data, no production credentials,
and no connection to any live system. A full threat model — including the
demo-only weaknesses and what production would require instead — is in
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## The demo passwords are public on purpose

```
ic.demo         / demo
ops.demo        / demo
logistics.demo  / demo
```

They are printed in the README, seeded from `fixtures/operators.json`, and
committed to this repository. That is safe **only** because:

- every account is fictional,
- the deployment is local, and
- `DEMO_MODE=true` gates the seeded operators and the operator-listing endpoint.

**Never reuse these anywhere real.** Never set `DEMO_MODE=false` and expect this
authentication to be adequate — it is not, and it is not meant to be. It has no
identity provider, no MFA, no lockout, no rate limiting, and no session
revocation.

## No secrets in this repository

- `.env` is git-ignored; only `.env.example` is committed, and it contains no
  values.
- The default configuration requires **no API key**. With `LLM_PROVIDER=none`
  the application makes no outbound network request at all.
- `LLM_API_KEY` and `DEMO_JWT_SECRET` are read from the environment and are
  blank by default. When `DEMO_JWT_SECRET` is blank, a random secret is
  generated per process, so tokens do not survive a restart and are worthless
  anywhere else.
- Before the first public commit the tree was swept for emails, phone numbers,
  private IP addresses, API-token shapes, `.env` files, private keys, agency
  hostnames, and production connection strings.

If you ever find a real-looking credential in this repository, treat it as a
finding and report it privately — see below.

## Reporting a vulnerability

Please report privately rather than opening a public issue:

1. **Preferred:** open a
   [private security advisory](https://github.com/AliDousa/aether-eoc-reference/security/advisories/new)
   on this repository.
2. Alternatively, contact the maintainer through the profile at
   [github.com/AliDousa](https://github.com/AliDousa).

Please include what you found, how to reproduce it, and what you think the
impact is.

**What counts as a finding here.** Because this is a demo with no real data, most
issues are software defects rather than incidents. The findings I would most want
to hear about, in order:

1. **Anything resembling real data** — a real person, place, incident, agency
   hostname, or credential appearing anywhere in this repository or its history.
   This would be a genuine problem and I would want to know immediately.
2. **A path from an agent to a resource mutation.** If any code path lets an
   agent move stock without a human decision, the central claim of this
   repository is false. That is the bug I care most about.
3. **A way to bypass the ICS authority checks**, the equity floor, or the audit
   chain.
4. Ordinary web vulnerabilities — injection, traversal, XSS, SSRF.

Please **do not** report the weaknesses already documented in
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) as vulnerabilities. The token in
`localStorage`, the WebSocket token in a query string, the trivial demo auth, and
the fact that the audit log is tamper-*evident* rather than tamper-*proof* are all
known, deliberate, and explained. A suggestion for how a production system should
handle them is welcome as an issue.

## Response

This is a personal portfolio project maintained in spare time, so there is no
formal SLA. I will acknowledge a report as soon as I reasonably can. Anything in
category 1 above will be dealt with immediately.

## Scope

In scope: this repository's code, fixtures, workflows, and git history.

Out of scope: any real system referenced in the documentation, third-party
dependencies (report those upstream), and denial of service against a demo
intended to run on `localhost`.
