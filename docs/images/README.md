# Screenshots

**No screenshots are committed here.** That is a decision, not an omission.

## Why not

- **A screenshot of a synthetic demo adds nothing you cannot see by running it.**
  `make install && make seed && make dev` takes about two minutes, and then the
  board is live and clickable rather than a picture of a board.
- **Screenshots drift.** They are the first thing to go stale after a UI change,
  and a reference repository whose images no longer match its code is actively
  misleading.
- **They add weight to a clone** for no functional benefit.
- **A screenshot travels without its context.** The `SYNTHETIC DEMO` banner is on
  every page precisely because images escape the repository that explains them;
  not producing extra images is the same instinct applied one step earlier.

## If you want them

Every screen is reachable without signing in, so no setup is needed beyond
running the stack:

| File to produce | Route | What to capture |
|---|---|---|
| `board.png` | `/` | Incident header, KPIs, ICS section chips, activity stream, request queue |
| `recommendation.png` | `/requests/<immediate request id>` | The three-leg allocation, the shortfall badge, the equity review, the decision controls |
| `audit.png` | `/audit` | The chain-verified strip, `ai.*` filter, and a row's before/after JSON drawer |
| `agents.png` | `/agents` | The will / will-not contracts and the run history with prompt hashes |
| `knowledge.png` | `/knowledge` | The DEMO PROTOCOL notice and a cited section |

```bash
make reset && make dev     # start from a known state so the figures match the docs
```

The most informative single image is the recommendation card mid-decision: it
shows an AI proposal, an explicit shortfall, a protected high-need site, and the
human controls that have not yet been used — which is the whole argument of this
repository in one frame.

If you generate a set worth keeping, drop them in this directory and link them
from the README. Please regenerate rather than retouch, and keep the
`SYNTHETIC DEMO` banner visible in every frame.
