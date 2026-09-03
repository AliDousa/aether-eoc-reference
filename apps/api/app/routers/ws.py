"""WebSocket endpoint for the live board.

The token arrives as a query parameter rather than an ``Authorization`` header
because the browser WebSocket API cannot set headers. That is a real weakness —
query strings land in logs — and it is why ``docs/THREAT_MODEL.md`` lists
short-lived ticket exchange as the production fix. For a synthetic demo whose
passwords are published, it is an acceptable simplification stated out loud.

Anonymous connections are allowed and appear as observers, so the board is
live for a reviewer who has not logged in yet.
"""

from __future__ import annotations

import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.clock import iso, now
from app.ids import new_id
from app.realtime import hub
from app.security import decode_token

router = APIRouter(tags=["realtime"])


@router.websocket("/api/ws/incidents/{incident_id}")
async def incident_socket(websocket: WebSocket, incident_id: str, token: str | None = None) -> None:
    await websocket.accept()

    user = decode_token(token) if token else None
    connection_id = new_id("con")
    display_name = user.display_name if user else "OBSERVER"
    ics_role = user.ics_role.value if user else "observer"
    operator_id = user.id if user else f"anon_{connection_id}"

    await hub.connect(
        websocket,
        incident_id=incident_id,
        connection_id=connection_id,
        operator_id=operator_id,
        display_name=display_name,
        ics_role=ics_role,
        announce=False,
    )

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "at": iso(now()),
                    "payload": {
                        "connection_id": connection_id,
                        "incident_id": incident_id,
                        "authenticated": user is not None,
                        "display_name": display_name,
                        "presence": hub.presence(incident_id),
                    },
                }
            )
        )

        # Only now tell everyone (including this socket) who is on the board.
        await hub.announce_presence(incident_id)

        # The client sends nothing but keepalives; this loop exists to detect
        # disconnects so presence stays accurate.
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong", "at": iso(now()), "payload": {}})
                )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - any transport failure ends the session
        pass
    finally:
        await hub.disconnect(incident_id=incident_id, connection_id=connection_id)
        with contextlib.suppress(Exception):
            await websocket.close()
