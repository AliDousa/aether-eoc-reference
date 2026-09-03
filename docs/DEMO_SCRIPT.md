# Demo script

Eight steps, about ten minutes. Everything below works with **no API key**.

Start from a clean seed so the numbers match:

```bash
make reset && make dev
```

Then open <http://localhost:3000>.

---

## 1. The board loads, and says what it is

**Do:** open the app.

**Expect:**

- An amber bar across the top: **SYNTHETIC DEMO — not a live EOC. All data is
  fictional.** It is not dismissible, and it is on every page.
- Incident **HEAT-2026-DUBAI-REF**, severity `MAJOR`, operational period **OP-2**
  with a countdown, commander **IC-Demo**.
- KPIs: **4** open requests · **1** unfilled IMMEDIATE · **3** sites below
  reorder · **0** pending AI reviews.
- ICS section chips: Command, Operations, Planning, Logistics — and
  **Finance / Admin marked `n/i`**, meaning present in the structure but not
  implemented in this slice.
- **27** activity entries spanning the last six hours, newest first.
- Bottom-right of the header: **Live updates on**. That is the WebSocket.

**Point of the step:** the demo announces its own limits — the banner, and a
section chip that admits it is unimplemented rather than faking cost capture.

---

## 2. Switch role to Logistics

**Do:** top right, choose **LOG** (or the role menu → Logistics).

**Expect:**

- The chip reads `LOGISTICS-1 · Logistics`.
- The menu footer says **"May approve logistics recommendations."**
- The presence rail adds your avatar alongside three dashed avatars —
  `OPERATIONS-2`, `LOGISTICS-2`, `PLANNING-1`. Dashed means simulated, and
  hovering says so.
- The request table's column order changes: Logistics leads with item, quantity,
  and shortfall.

**Point of the step:** this is a real login as a different seeded operator, not a
client-side filter. Authority actually changes — which step 4b proves.

---

## 3. Open the IMMEDIATE request that cannot be filled

**Do:** click the row badged **IMMEDIATE** — 400 kits of Oral Rehydration Salts
to Sector North Cooling Center.

**Expect:**

- State **Submitted**; justification explaining Sector North holds 25 kits
  against a reorder point of 80.
- Destination marked **equity priority 5 of 5** — the highest-need site.
- A **Timeline** panel on the right, drawn from the audit log.
- No recommendation yet.

**Optional, worth doing:** open **Requests** → the ORS line. Central Cache has
180 available, Field Staging 90, Sector South 60. That is 330 against a request
for 400 — and Sector South is itself below its reorder point.

---

## 4. Ask the recommender — and watch inventory *not* change

**Do:** click **Ask recommender**.

**Expect** a recommendation card with:

- Badge **Awaiting human**, and the banner *AI-suggested — verify with current
  official guidance. Nothing moves until a human approves it.*
- A three-leg allocation:

  | Source | Equity | Available | Move | Leaves |
  |---|---|---|---|---|
  | Field Staging | eq1 | 90 | 90 | 0 |
  | Central Cache | eq2 | 180 | 180 | 0 |
  | Sector South Cooling Center | eq4 | 60 | 40 | 20 |

- **Short 90 kit** and **Equity floor OK**.
- Equity review: *"Sector South Cooling Center: Equity priority 4 site retains 20
  unit(s) under the equity floor."*
- Citations to `resource-allocation-equity-rules.md`.
- Request state moves to **Awaiting decision**.

**Now check the important thing:** open **Requests** (or the board) and look at
ORS stock. It is unchanged — 180 / 90 / 60. The agent proposed; nothing moved.

**Point of the step:** the shortfall is stated rather than rounded away, the
high-need site is capped rather than drained, and the proposal has no power to
execute itself.

---

## 4b. Confirm the guardrail is real (30 seconds, worth it)

**Do:** switch role to **OPS**, and look at the recommendation card.

**Expect:** **Approve** and **Reject** are disabled, with the reason written out:
*"The operations section does not hold authority to commit resources… The server
enforces this — the buttons below are not the control."*

That last sentence is literally true — `POST /api/recommendations/{id}/decide` as
Operations returns **403**, tested in
`tests/api/test_recommendation_guardrails.py`.

**Do:** switch back to **LOG**.

---

## 5. Modify, then approve

**Do:** in the **Move** column, reduce the **Central Cache** leg from 180 to
**100**. Type a reason — for example *"Holding 80 at Central Cache for the OP-3
handover."* — then click **Modify and approve**.

Note the button label changed from *Approve as recommended* the moment you
edited a quantity. Editing **is** modifying; there is no separate mode to find.

**Expect:**

- Request state → **Modified + approved**; recommendation → **Modified by human**.
- Inventory moves: Field Staging 90 → 0, Central Cache 180 → 80, Sector South
  60 → 20, and Sector North gains 230.
- The activity stream gains a movement entry, live, without a refresh.
- The **Human decision** panel records who, when, and the reason.

**Point of the step:** the system distinguishes *the human agreed* from *the
human changed it*, and stores both the proposed plan and the approved one. That
distinction is the whole evidence that a person was actually in the loop.

**Try the guardrail directly (optional):** instead of reducing a leg, set the
**Sector South** leg to its full 60. The API returns **409** with
*"Would leave 0 at an equity priority 4 site; the floor requires at least 20."*
Logistics cannot override it. Only an Incident Commander can, and only with a
written reason — which is recorded.

---

## 6. Run the Situation Assessment as IC

**Do:** switch to **IC**, go to **Agents**, click **Run situation summary**.

**Expect:**

- Mode chip **AI · rules** and model `deterministic-rules-v1` — no key needed.
- A SITREP-shaped output: current situation, objectives, resource status, pending
  decisions.
- **What this does not know** — a non-empty list of information gaps. It can
  never be empty; `knowledge/ics-sitrep-template.md` §6 makes it mandatory.
- Eight citations: six activity event ids plus two knowledge sections.
- In **Recent runs**: mode, status, chunk count, latency, and a **prompt hash**.
  The prompt itself is never stored — only its SHA-256.

---

## 7. Ask the Protocol Retriever

**Do:** on the same page, ask **"When do we open a second cooling center?"**
(it is the first suggested question).

**Expect:**

- The verify banner above the answer.
- Top citation
  `cooling-center-activation-checklist.md#2-when-to-open-a-second-cooling-centre-in-a-sector`.
- The actual thresholds quoted, not paraphrased — 80 % occupancy for 60 minutes,
  **any** turn-away, 20-minute travel time, 10 presentations/hour, and the
  forecast rule.
- Uncertainty stating the corpus is a demo artefact with no revision date.

**Then verify the citation by hand:** open **Knowledge** →
`cooling-center-activation-checklist.md` and read section 2. It says exactly
that. Note the query said *center* and the document says *centre* — the tokenizer
folds the variants.

**Point of the step:** the citation is checkable. That is what separates a
citation from decoration.

---

## 8. Read the audit log

**Do:** open **Audit**.

**Expect:**

- **Audit chain verified**, *"Verified N rows from genesis"*, with a head hash.
  A fresh seed is 29 rows; your walkthrough will have added to it.
- Filter **`ai.*`** — every agent invocation, including the two seeded ones and
  the runs you just triggered.
- Filter **`inventory.*`** — every stock movement. Two from the seeded water
  approval, plus the legs you approved in step 5.
- Filter **`recommendation.*`** — the human decisions, including the seeded
  rejection.
- Click any row: before/after JSON, correlation id, and an **AI trace** id
  linking the movement back to the advice that informed it.

**Prove the chain means something (optional, ~1 minute):**

```bash
sqlite3 data/eoc.db "UPDATE audit_events SET after_json='{\"tampered\":true}' WHERE seq=3;"
curl -s localhost:8080/api/audit/verify
```

Returns `"ok": false` and names `broken_at_seq: 3`. Reload the Audit page and the
strip reads **Audit chain BROKEN**. Then `make reset` to restore.

**Point of the step:** "immutable audit log" is a claim you just tested, not one
you were asked to believe.

---

## What you have now confirmed

1. Which legacy-EOC problems this attacks — and the banner admitting what it is.
2. It runs from one documented command path, with no keys.
3. The board updates live.
4. An AI recommendation appears and **cannot execute** until a human approves it.
5. Every state change, AI suggestion, and human decision is in one verifiable log.
6. Six ADRs explain the hard choices — including what was left undone.
7. Nothing resembles real agency data, real patients, or a live integration.

Sixty seconds more, if you have them: read `app/inventory.py` (the only place
stock changes) and `app/audit.py` (the chain). Between them they are about 350
lines, and they are the argument.
