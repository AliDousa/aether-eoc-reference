"""Time helpers.

SQLite has no native timezone-aware storage, so values round-trip as naive
datetimes even when written as aware UTC. Every read path goes through
`as_utc` so the rest of the codebase can assume aware UTC and never has to
reason about which driver it is talking to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Offset applied to every `now()` call. Zero in normal operation.
#
# The seeder walks this backwards to six hours before the present and then
# steps it forward, so the seeded incident has a believable six-hour history
# instead of every row sharing one timestamp. Doing it here rather than by
# rewriting rows afterwards keeps the audit hash chain valid, since each row's
# timestamp is part of what it commits to.
_offset: timedelta = timedelta(0)


def now() -> datetime:
    """Current time as an aware UTC datetime, plus any seeding offset."""
    return datetime.now(UTC) + _offset


def set_offset(delta: timedelta) -> None:
    """Shift the clock. Used only by the seeder; reset to zero when done."""
    global _offset
    _offset = delta


def advance(delta: timedelta) -> None:
    """Move the seeding clock forward."""
    global _offset
    _offset += delta


def reset_offset() -> None:
    set_offset(timedelta(0))


def as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive datetime; convert an aware one to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: datetime) -> str:
    """Canonical ISO-8601 rendering used in audit hashes and API payloads."""
    return as_utc(value).isoformat().replace("+00:00", "Z")
