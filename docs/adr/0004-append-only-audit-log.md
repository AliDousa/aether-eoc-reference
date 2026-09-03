# ADR-0004: An append-only, hash-chained audit log

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

After an incident there is a review. Sometimes it is a debrief; sometimes it is
an inquiry. The question is always some version of: *who decided this, on what
information, and when?*

Legacy EOC-class systems answer this poorly. State is often overwritten in
place, "who changed it" is a `last_modified_by` column, and the reasoning behind
a decision lives in someone's memory or a separate email thread. Once an AI
system is proposing resource movements, that gap stops being an inconvenience
and becomes a governance problem: an unexplainable allocation is one nobody can
defend.

This repository claims an *immutable* audit log. A plain append-only table
cannot support that claim — nothing about it makes tampering detectable.

## Decision

One `audit_events` table, written **only** by `app.audit.record`, with:

- No update path and no delete path anywhere in the codebase.
- A monotonic `seq` primary key, so the log has a total order.
- A hash chain over the fields a caller controls:

  ```
  hash(n) = SHA256( hash(n-1) || canonical_json(row(n)) )
  ```

  with a genesis value of 64 zeroes.
- `before_json` / `after_json` state snapshots, so a reviewer can diff the change.
- A `correlation_id` tying together every write caused by one user action, and a
  nullable `ai_trace_id` linking a row to the agent run that informed it.
- `GET /api/audit/verify`, which replays the chain from genesis and reports the
  first divergence by sequence number.

Audit rows join the same transaction as the change they describe, so a
rolled-back mutation cannot leave an audit row claiming it happened.

## Rationale

- **A verifiable claim beats a stated one.** "Append-only" is a promise about
  code. A hash chain is a property a reviewer can test: edit any historical row
  and `/api/audit/verify` names the sequence number that broke.
- **The chain is what makes demo step 8 meaningful.** Filtering `ai.*` and
  `inventory.*` and seeing an unbroken sequence is only interesting if
  "unbroken" is checkable.
- **Canonical JSON matters.** Sorted keys, no whitespace, ISO-8601 timestamps —
  so the same logical row hashes identically regardless of dict ordering or
  Python version. Without this the chain would be spuriously fragile.
- **Correlation ids make the log readable as a story.** One approval writes a
  decision row, a state-change row, and a transfer row. Sharing a correlation id
  turns three rows into one event.
- **Audit rows are for actions, not narration.** An earlier iteration wrote an
  audit row for every activity-stream entry, including entries that merely
  narrated an already-audited state change. That buried the `ai.*` and
  `inventory.*` rows the log exists to make findable. Now the activity stream
  carries the human-readable narrative and the audit log carries accountability.

## Alternatives considered

**A plain append-only table with no chain.** Simpler, and the honest description
would then be "append-only by convention". Rejected because the repository
description says *immutable*, and a claim you cannot check should not be made.

**Per-row digital signatures.** Stronger — it would bind a row to a signing key
rather than merely to its predecessor. Rejected as out of scope: it needs key
management, which is a production concern with no demo value here.

**Event sourcing as the primary model.** Rejected. Rebuilding all state from an
event log is a much larger commitment, and it would make the request board
harder to read, not easier.

**Writing to an external append-only store (S3 Object Lock, a WORM bucket).**
This is the genuinely correct production answer and is recorded as such. Rejected
here because it requires cloud credentials.

## Consequences

**Accepted — and this matters:**

- **This is tamper *evidence*, not tamper *proofing*.** Anyone who can write to
  the database can also recompute the chain from the point they altered, and
  verification would pass. The chain detects careless or partial tampering; it
  does not defeat an attacker with write access. Real tamper-proofing requires
  the log to leave the trust boundary — an append-only external store, a signed
  and externally-witnessed digest, or both. `docs/THREAT_MODEL.md` says this
  plainly, and so does the module docstring in `app/audit.py`.
- **Chain appends are serialised by an `asyncio.Lock`**, which is correct for one
  process and wrong for several: two processes could read the same predecessor
  hash and fork the chain. A multi-process deployment needs a database sequence
  or a single writer.
- Verification is O(n) and reads the whole table. Fine at demo size; a large log
  would need periodic checkpointing.

**Gained:**

- Every state change, every AI suggestion, and every human decision are in one
  ordered, verifiable sequence.
- The request detail timeline is rendered *from the audit log*, so the story a
  reviewer reads and the record an auditor reads are the same data.

## Implementation notes

- `app/audit.py` is ~200 lines and worth reading in full.
- `snapshot()` serialises an ORM instance from its mapped columns, so audit call
  sites do not hand-list fields and then drift.
- The seeder replays its history through the real service functions, so the
  seeded audit log is genuine: 29 rows on a fresh seed, verifying from genesis.
- Action names use a dotted namespace — `request.*`, `inventory.*`,
  `recommendation.*`, `ai.*`, `activity.*`, `auth.*` — so prefix filtering works
  with a single query parameter.
