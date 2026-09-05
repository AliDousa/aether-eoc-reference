# Agent specification

> **Synthetic demonstration.** With `LLM_PROVIDER=none` — the default — no model
> is contacted and every agent below produces deterministic, rule-derived
> output. The full walkthrough works offline.

Design rationale is in
[ADR-0005](adr/0005-supervisor-specialist-agents-with-hitl.md). This document is
the contract.

## Supervisor

`app/agents/supervisor.py`. A plain module, not a framework.

**Responsibilities.** Route an intent to exactly one specialist; assemble the
inputs that specialist is permitted to see; build the redaction map; persist the
run; decide whether the output may act.

**Refuses** any intent outside this table rather than guessing:

| Intent | Specialist | Acts? |
|---|---|---|
| `situation_summary` | Situation Assessment | No — advisory |
| `protocol_question` | Protocol Retriever | No — advisory |
| `resource_recommendation` | Resource Recommender | **No — `awaiting_human`** |

**Specialists never call each other.** They are side-effect-free async functions
that take values and return an `AgentResult`; they hold no database session, so
"the agent cannot write" is enforced by what it is handed, not by discipline.

**Persisted for every run** (`agent_runs` table):

| Field | Why |
|---|---|
| `mode` | `fixture` or `llm` — which path actually produced this |
| `model_id` | `deterministic-rules-v1`, or the real model |
| `prompt_hash` | SHA-256 of the exact prompt sent. The prompt itself is **not** stored: enough to prove which inputs produced an output, without copying incident text into a second place |
| `retrieved_chunk_ids` | Every source consulted |
| `raw_output` / `structured_output` | What came back, and its parsed form |
| `status` | `complete`, `awaiting_human`, or `failed` |
| `latency_ms`, `requested_by`, `correlation_id` | Who asked, when, as part of what action |

Each run also writes an `ai.*` audit row carrying the run id as `ai_trace_id`,
so any downstream decision links back to the advice that informed it.

---

## 1. Situation Assessment

**Purpose.** Summarise the incident and recent activity in the shape of
`knowledge/ics-sitrep-template.md`.

**Will**
- Produce SITREP sections 2–5 (current situation, objectives, resource status,
  pending decisions).
- Cite the activity events it read, by id, plus the template sections used.
- **Always** state information gaps. The list can never be empty.

**Will not**
- Move resources, or recommend a specific allocation.
- Give clinical advice.
- Report an objective as met without evidence. "No reports received" is a gap,
  not a success.

**Inputs.** Incident header; last 20 activity events; open requests; inventory
positions below reorder; count of pending recommendations.

**Output** (`structured`):

```jsonc
{
  "incident": "HEAT-2026-DUBAI-REF",
  "period": "OP-2",
  "sections": [{ "title": "2. Current situation", "body": "…" }],
  "unfilled_immediate": 1,
  "sites_below_reorder": [{ "site_name": "…", "sku_name": "…",
                            "available": 25, "reorder_point": 80 }],
  "pending_reviews": 0,
  "events_considered": ["act_5659b4fd", "…"]
}
```

**Model use.** When a key is configured, the model writes **section 2 only**.
The structured facts, citations, and gaps are computed either way — so a model
outage changes the tone of one paragraph and nothing else.

**Confidence.** Capped at 0.70–0.74. This is a summary of a partial picture, and
presenting it as near-certain would teach the wrong lesson.

**Fallback.** Deterministic paragraph assembled from the same facts.

**Evaluation notes.** Check that: every cited event id exists; the gaps list is
non-empty; unfilled-IMMEDIATE and below-reorder counts match the board.

---

## 2. Protocol Retriever

**Purpose.** Answer protocol questions from the bundled synthetic corpus, and
nothing else.

**Will**
- Retrieve with BM25 over heading-delimited chunks of `knowledge/*.md`.
- Quote thresholds and numbers exactly as written.
- Cite chunk ids that resolve on disk — verifiable at
  `GET /api/knowledge/chunk?id=…` and browsable on the Knowledge page.
- Carry the banner `AI-suggested — verify with current official guidance.`
- **Say it does not know** when nothing scores above threshold.

**Will not**
- Answer from parametric knowledge. A confident answer with no source is the
  most dangerous output an EOC assistant can produce.
- Give clinical advice, or imply official authority.

**Sources.** Exactly four files, all invented for this repository:
`cooling-center-activation-checklist.md`,
`resource-allocation-equity-rules.md`,
`heat-illness-field-protocol.md`,
`ics-sitrep-template.md` — 29 retrievable sections.

**Output** (`structured`):

```jsonc
{
  "question": "When do we open a second cooling center?",
  "answered": true,
  "banner": "AI-suggested — verify with current official guidance.",
  "chunks": [{ "id": "cooling-center-activation-checklist.md#2-when-to-open-a-second-cooling-centre-in-a-sector",
               "title": "2. When to open a SECOND cooling centre in a sector",
               "score": 8.64 }]
}
```

**Retrieval notes.** Okapi BM25 (k1 = 1.5, b = 0.75) with a 1.25× heading boost
per matched title term, and a small spelling-normalisation map so `center` and
`centre` are one token. Lexical rather than dense **on purpose**: a reviewer can
read `app/rag.py`, read the corpus, and confirm by hand that a cited chunk says
what the agent claims. `EMBEDDING_PROVIDER` is reserved as the extension point
and is **not implemented** in this slice.

**Fallback.** With no model the answer is *extractive* — the retrieved sections
are quoted directly. More accurate and more checkable than a paraphrase.

**Evaluation notes.** "When do we open a second cooling center?" must rank
`#2-when-to-open-a-second-cooling-centre-in-a-sector` first; an out-of-corpus
question must return the no-answer response, not an invention.

---

## 3. Resource Recommender

**Purpose.** Propose how to fill a resource request from available stock,
respecting the equity floor.

**Will**
- Draw in the order set by `resource-allocation-equity-rules.md` §4: reserve and
  staging sites (equity 1–2) first, then baseline (3) down to its reorder point,
  then high-need (4–5) only while staying strictly above zero and above 25 % of
  reorder point.
- **State shortfalls explicitly.** Never round one away.
- Show which sites were considered and what was withheld, and why.
- Cite the rule that produced the outcome — always including the equity floor,
  even if BM25 ranked another section higher.
- Stop before execution. Always.

**Will not**
- Write inventory. **There is no import path from this module to
  `app.inventory`.**
- Reduce a site with equity priority 4–5 to zero to serve a lower-priority site.
- Override the equity floor. Only an Incident Commander may, and only with a
  written reason.

**Inputs.** SKU, quantity, priority, and the candidate source sites for that SKU
(the destination is excluded), each with equity priority, available stock, and
reorder point.

**Output** (`structured`):

```jsonc
{
  "sku_code": "ORS-KIT",
  "destination_site_id": "site_north",
  "requested_quantity": 400,
  "allocated_quantity": 310,
  "shortfall": 90,
  "fully_filled": false,
  "legs": [
    { "from_site_id": "site_staging", "from_site_name": "Field Staging",
      "quantity": 90, "equity_priority": 1,
      "available_before": 90, "available_after": 0 }
  ],
  "notes": ["Shortfall of 90 unit(s). The equity floor prevents drawing further…"],
  "equity_review": {
    "passed": true,
    "rule_id": "resource-allocation-equity-rules.md#3-the-equity-floor-hard-constraint",
    "summary": "Equity floor satisfied, but it caps the fill.",
    "considered": [ /* every candidate, with max_draw and what was drawn */ ],
    "withheld":  [{ "site_name": "Sector South Cooling Center",
                    "equity_priority": 4, "retained": 20,
                    "reason": "Equity priority 4 site retains 20 unit(s) under the equity floor." }],
    "violations": []
  }
}
```

**Guardrails, in order of application:**

1. **Proposal time.** The planner cannot emit a leg that breaches the floor.
   Protected stock is recorded in `withheld` even when it was not needed, so the
   review shows the floor was *applied* rather than coincidentally unbreached.
2. **Decision time.** `validate_legs` re-runs the floor against **current** stock.
   A human edit gets the same scrutiny; a stale plan cannot slip through.
3. **Authority.** `require_decision_authority` runs before anything else.
4. **Override.** Only `recommendation:decide:any` (Incident Commander) plus an
   explicit flag plus a written reason, recorded in the audit log.

**Model use.** **None, by design.** An allocation is arithmetic against a written
rule; a language model would add variance without adding correctness and would
make the guardrail harder to verify.

**Confidence.** 0.86 when fully filled, 0.62 when short.

**Evaluation notes.** The seeded scenario is the regression test: 400 ORS kits to
Sector North must produce 310 across three sites, a shortfall of 90, and Sector
South retaining 20. Covered by `tests/api/test_equity_guardrail.py`, including
the fail-closed case where the only source is a high-equity site.

---

## Redaction

`app/agents/redact.py`, applied before **every** outbound model call, whether or
not the data needs it.

1. **Display names → role tokens.** `LOGISTICS-1` → `LOGISTICS-1`; a real name
   would become `LOGISTICS-2`-style. Longest names substituted first so an
   overlapping shorter name cannot half-replace a longer one.
2. **Pattern scrubbing.** Emails, phone numbers, digit runs of nine or more,
   IPv4 addresses, URLs.
3. **Tripwire.** `assert_clean` re-checks the redacted text. If anything
   survives, the call is **not made** and the deterministic path is used.

The seeded fixtures contain nothing worth protecting. The redactor runs anyway,
because the useful property of a reference implementation is that the boundary
is visible and unconditional.

## Testing

Run with no API key:

```bash
make test        # 18 API tests + 14 web tests
```

The guardrail assertions specifically: a recommendation does not mutate
inventory; the approve path mutates exactly once and writes both a decision row
and a transfer row; the equity check fails closed; every emitted citation
resolves on disk; Operations cannot commit resources.
