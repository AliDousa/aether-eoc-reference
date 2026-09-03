"""Human-readable identifiers.

Reference repositories are read more than they are run. Prefixed ids
(`req_4f2a9c81`) make API responses, audit rows, and WebSocket frames legible
without cross-referencing a table, which matters more here than the storage
efficiency of a raw UUID.
"""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Return a short prefixed identifier, e.g. ``req_4f2a9c81``."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def correlation_id() -> str:
    """Identifier tying together every write caused by one user action."""
    return new_id("cor")
