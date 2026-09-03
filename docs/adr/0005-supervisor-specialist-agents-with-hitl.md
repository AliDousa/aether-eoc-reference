# ADR-0005: A supervisor with narrow specialists, and a human in the loop

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

"AI for emergency management" is currently marketed as autonomy: the system
notices a shortage and dispatches the trucks. In an actual public-health
emergency that is the wrong product. Resource decisions carry legal authority,
professional accountability, and equity consequences. The Incident Commander
owns them, and an audit trail that ends at "the model decided" is not a defence.

The useful contribution of a model here is narrower and more valuable: assemble
the picture faster, find the relevant protocol, and propose an allocation with
its reasoning exposed — then stop.

A second constraint shapes everything: the demo must work with **no API key**.
If the interesting behaviour requires a paid credential, most reviewers never
see it.

## Decision

A **supervisor** routes an intent to exactly **one specialist**. Specialists
never call each other and never write.

| Agent | Intent | Acts? |
|---|---|---|
| Situation Assessment | `situation_summary` | No — advisory |
| Protocol Retriever | `protocol_question` | No — advisory |
| Resource Recommender | `resource_recommendation` | **No — held for a human** |

Rules, enforced in code:

1. **Any output that would change resources, public communications, or policy is
   persisted with status `awaiting_human`** and materialised as a
   `Recommendation` in `pending`. It cannot execute.
2. **No agent module imports `app.inventory`.** The guardrail is structural, not
   procedural.
3. Every run persists: mode, model id, prompt SHA-256, retrieved chunk ids, raw
   output, structured output, latency, actor, correlation id.
4. **Fixture mode is the default.** With `LLM_PROVIDER=none` every agent produces
   deterministic, rule-derived output and the entire walkthrough works offline.
5. **Redaction runs before any outbound call**, unconditionally, with a tripwire
   that refuses to send if a contact-detail or identifier pattern survives it.

The supervisor is a plain ~250-line Python module. No agent framework.

## Rationale

- **The human-in-the-loop gate is the product.** Everything else here is
  ordinary CRUD. The distinguishing claim is that an AI suggestion and a human
  decision are different objects, both recorded, and only the second one moves
  anything.
- **A recommendation and its decision are stored separately.** `payload_json` is
  what the agent proposed; `decided_payload_json` is what the human approved.
  Keeping both is what makes "modified" distinguishable from "approved" — and
  that distinction is the entire evidence that a human was actually in the loop
  rather than clicking through.
- **The recommender is deterministic even when a model is available.** An
  allocation is arithmetic against a written rule. A language model would add
  variance without adding correctness, and would make the equity guardrail
  harder to verify. The model path exists for the two narrative agents, where
  prose quality is the actual value.
- **No framework.** LangGraph and similar are good tools for graphs with cycles,
  retries, and tool negotiation. This is a three-way switch with typed inputs.
  A framework would add a dependency, an abstraction layer, and vocabulary a
  reviewer has to learn, in exchange for replacing a `if intent == ...` block.
  Clarity is the deliverable (ADR-0001).
- **Fixture mode is not a fallback, it is the default.** Any LLM failure —
  missing key, timeout, HTTP error, redaction tripwire — degrades to the
  deterministic path rather than surfacing an error. An operational tool that
  breaks when a vendor endpoint is slow is worse than one that says "model
  unavailable, here is the rule-based answer".
- **Uncertainty is mandatory output.** The Situation Assessment agent can never
  return an empty gaps list. `knowledge/ics-sitrep-template.md` §6 requires it,
  and an assessment that admits nothing is precisely the failure this repo
  argues against.

## Alternatives considered

**Autonomous execution with a rollback window.** Rejected outright. "It will
un-deploy the ambulances if you object within five minutes" is not consent, and
resource movements are not reversible in the way that database rows are.

**LangGraph or a comparable framework.** Rejected: see above. Reconsider if the
agent graph ever gains cycles or genuine tool negotiation.

**A single general-purpose agent with tools.** Rejected. Narrow agents with
written "will / will not" contracts are auditable; a general agent's boundary is
whatever its prompt happened to say that day. The Agents page renders the
will-not list with equal weight to the will list, because for an operational
tool the boundary *is* the specification.

**Requiring an API key.** Rejected as fatal to the repo's purpose.

**Vector search for retrieval.** Rejected for this slice; see ADR-0006's sibling
reasoning in `app/rag.py`. BM25 over four Markdown files is verifiable by hand,
needs no key, and a reviewer can check that a cited section really says what the
agent claims.

## Consequences

**Accepted:**

- Fixture-mode prose is templated and reads like it. That is the correct trade:
  a reviewer can predict the output exactly, which makes the guardrails easy to
  see.
- BM25 will miss a paraphrase that an embedding model would catch. Mitigated
  with a small spelling-normalisation map (`center`/`centre`) and a heading
  boost. `EMBEDDING_PROVIDER` is reserved as the extension point and is
  **documented as not implemented** rather than implied.
- The supervisor is a switch, so adding an agent means editing it. At three
  agents this is a feature.

**Gained:**

- The whole demo runs offline, deterministically, and in CI with no secrets.
- "The AI cannot move stock" is verifiable by grep, not by trust.

## Implementation notes

- `app/agents/supervisor.py` — routing, input assembly, persistence, the HITL
  gate.
- `app/agents/recommender.py` — the allocation planner and equity floor, written
  as pure functions over `Candidate` values so they are testable without a
  database or a model.
- `app/agents/redact.py` — display names to role tokens (`LOGISTICS-2`), then
  pattern scrubbing for emails, phone numbers, long digit runs, IPs, and URLs.
- `app/agents/llm.py` — the optional path. Uses `httpx` directly rather than the
  vendor SDKs, keeping the dependency surface honest about what the demo needs.
- Enabling a model:

  ```bash
  LLM_PROVIDER=anthropic
  LLM_API_KEY=sk-...
  LLM_MODEL=claude-sonnet-5
  ```

  The Agents page then shows `AI · model` instead of `AI · rules`, and agent
  runs record the real model id.
