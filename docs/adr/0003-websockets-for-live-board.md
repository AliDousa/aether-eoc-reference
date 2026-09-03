# ADR-0003: WebSockets for the live board, with REST as the source of truth

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

A shared incident board is only useful if it is shared *now*. The failure mode
of legacy WebEOC-class systems that operators complain about most is stale
state: two people looking at the same board, one of them acting on a picture
that changed four minutes ago, and neither knowing it.

So the board must update without a page refresh. The question is what the live
channel is *for*.

## Decision

Use **WebSockets** served by the same FastAPI process as the REST API, with an
in-process hub and no broker.

Critically: **frames are hints, not data.** On receiving a frame the client
invalidates the relevant TanStack Query keys and refetches over REST. The only
payload the client trusts from the socket is presence, which exists nowhere else.

Frame types: `connected`, `presence.updated`, `activity.created`,
`request.created`, `request.updated`, `inventory.updated`, `agent.completed`.

## Rationale

- **Correctness over cleverness.** Patching client state from event payloads
  means a dropped, duplicated, or out-of-order frame can leave the board showing
  something the server never said. On a screen people commit resources from,
  that is a correctness bug, not a cosmetic one. Refetching costs one request
  and removes the entire class of problem.
- **No keys, no accounts.** Liveblocks, Pusher, and Ably all require a hosted
  service and an API key. A reviewer must be able to clone and run this with
  nothing. That constraint alone rules them out.
- **Same process as the API.** The events originate from the service functions
  that already handle the writes. Routing them through a broker would add
  infrastructure without adding capability at this size.
- **Broadcast failures cannot fail a write.** Every broadcast goes through
  `safe_broadcast`, which suppresses exceptions. An approval that has been
  committed to the database must never be reported as failed because a socket
  died mid-send.
- **The client degrades visibly.** When the socket drops, the header shows
  "Offline — polling" in words, not just a colour, and a 20-second refetch
  interval keeps the board correct. A board that silently stops updating is
  more dangerous than one that never updated.

## Alternatives considered

**Server-Sent Events.** A reasonable fit — one-directional, simpler, reconnects
natively. Rejected mainly because presence needs the client to signal liveness,
and partly because a WebSocket is the shape a production build would take once
acknowledgements or client-side cursors appear.

**Polling only.** Simplest, and genuinely adequate at this data volume. Rejected
because "I can see the board update without refreshing" is one of the seven
things a reviewer is meant to be able to confirm.

**Redis pub/sub behind the hub.** Correct for multiple replicas, and rejected as
premature: it would add a required service to satisfy a scale requirement the
slice does not have.

## Consequences

**Accepted:**

- **A second API replica breaks fan-out.** Each process would hold its own
  subscriber set, so an event raised on replica A never reaches a client on
  replica B. Fixing this needs Redis pub/sub or equivalent. This is the single
  largest gap between this slice and a production deployment, and it is stated
  here rather than discovered later.
- Presence is process-local and lost on restart.
- The token is passed as a **query parameter**, because the browser WebSocket
  API cannot set headers. Query strings end up in logs. The production answer is
  a short-lived single-use ticket exchanged over HTTP; see `docs/THREAT_MODEL.md`.

**Gained:**

- Live board with no infrastructure.
- Simulated peer operators make presence legible to a lone reviewer, and are
  labelled as simulated so the demo does not imply colleagues who do not exist.

## Implementation notes

- `app/realtime.py` holds the hub; `app/routers/ws.py` is the endpoint.
- Registration and the presence broadcast are separated (`announce=False`) so a
  client always receives its own `connected` handshake before any board traffic.
- The client reconnects on a 3-second timer and sends a keepalive every 25
  seconds, so an API restart does not require a page reload.
- Anonymous sockets are accepted and appear as `OBSERVER`, so the board is live
  before a reviewer signs in.
