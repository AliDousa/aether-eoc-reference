"""In-process WebSocket hub: live board updates and presence.

One process, one hub, an in-memory subscriber set. No Redis, no broker
(ADR-0003). That is the right size for a reference slice and the wrong size
for production, where a fan-out tier is needed the moment there are two API
replicas — stated here so nobody has to guess whether the omission was
considered.

The client is expected to treat these frames as *hints*, not as the source of
truth: it refetches over REST on receipt. That keeps a dropped socket from
producing a subtly wrong board, which is the failure mode that matters when
people are making resource decisions.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from app.clock import iso, now
from app.enums import IcsRole


@dataclass
class PresenceEntry:
    """One operator viewing an incident."""

    connection_id: str
    operator_id: str
    display_name: str
    ics_role: str
    since: str
    # Simulated peers make the presence rail legible in a single-reviewer demo.
    # Flagged so the UI can label them rather than implying real colleagues.
    simulated: bool = False


# Synthetic colleagues so a lone reviewer sees a populated duty floor. Names are
# role-shaped by design (see docs/THREAT_MODEL.md): no invented humans.
SIMULATED_PEERS: tuple[PresenceEntry, ...] = (
    PresenceEntry(
        connection_id="sim-ops-2",
        operator_id="opr_sim_ops2",
        display_name="OPERATIONS-2",
        ics_role=IcsRole.OPERATIONS_SECTION.value,
        since="",
        simulated=True,
    ),
    PresenceEntry(
        connection_id="sim-log-2",
        operator_id="opr_sim_log2",
        display_name="LOGISTICS-2",
        ics_role=IcsRole.LOGISTICS_SECTION.value,
        since="",
        simulated=True,
    ),
    PresenceEntry(
        connection_id="sim-plan-1",
        operator_id="opr_sim_plan1",
        display_name="PLANNING-1",
        ics_role=IcsRole.PLANNING_SECTION.value,
        since="",
        simulated=True,
    ),
)


@dataclass
class Hub:
    """Fan-out registry keyed by incident id."""

    _sockets: dict[str, dict[str, WebSocket]] = field(default_factory=dict)
    _presence: dict[str, dict[str, PresenceEntry]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _started_at: datetime = field(default_factory=now)

    async def connect(
        self,
        websocket: WebSocket,
        *,
        incident_id: str,
        connection_id: str,
        operator_id: str,
        display_name: str,
        ics_role: str,
        announce: bool = True,
    ) -> None:
        """Register a socket. With ``announce=False`` the caller broadcasts
        presence itself, so the client's own handshake frame can be sent
        first — a client should never receive board traffic before it has
        been told it is connected."""
        async with self._lock:
            self._sockets.setdefault(incident_id, {})[connection_id] = websocket
            self._presence.setdefault(incident_id, {})[connection_id] = PresenceEntry(
                connection_id=connection_id,
                operator_id=operator_id,
                display_name=display_name,
                ics_role=ics_role,
                since=iso(now()),
            )
        if announce:
            await self.announce_presence(incident_id)

    async def announce_presence(self, incident_id: str) -> None:
        await self.broadcast(
            incident_id, "presence.updated", {"presence": self.presence(incident_id)}
        )

    async def disconnect(self, *, incident_id: str, connection_id: str) -> None:
        async with self._lock:
            self._sockets.get(incident_id, {}).pop(connection_id, None)
            self._presence.get(incident_id, {}).pop(connection_id, None)
        await self.broadcast(
            incident_id, "presence.updated", {"presence": self.presence(incident_id)}
        )

    def presence(self, incident_id: str) -> list[dict[str, Any]]:
        """Live viewers plus the simulated peers, live first."""
        live = [asdict(entry) for entry in self._presence.get(incident_id, {}).values()]
        peers = [asdict(peer) | {"since": iso(self._started_at)} for peer in SIMULATED_PEERS]
        return live + peers

    def connection_count(self, incident_id: str) -> int:
        return len(self._sockets.get(incident_id, {}))

    async def broadcast(self, incident_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Send one frame to every subscriber of an incident.

        Never raises: a board update must not be able to fail an approval that
        has already been committed. Dead sockets are dropped silently and the
        client reconnects.
        """
        frame = json.dumps({"type": event_type, "at": iso(now()), "payload": payload})
        async with self._lock:
            targets = list(self._sockets.get(incident_id, {}).items())

        dead: list[str] = []
        for connection_id, socket in targets:
            try:
                await socket.send_text(frame)
            except Exception:  # noqa: BLE001 - transport errors are expected churn
                dead.append(connection_id)

        if dead:
            async with self._lock:
                for connection_id in dead:
                    self._sockets.get(incident_id, {}).pop(connection_id, None)
                    self._presence.get(incident_id, {}).pop(connection_id, None)


hub = Hub()


async def safe_broadcast(incident_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Broadcast without letting realtime problems surface as request errors."""
    with contextlib.suppress(Exception):
        await hub.broadcast(incident_id, event_type, payload)
