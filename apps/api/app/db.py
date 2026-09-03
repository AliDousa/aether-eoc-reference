"""Database engine and session wiring.

SQLite is the default so the demo has zero operational dependencies
(ADR-0002). The only SQLite-specific concession is the ``foreign_keys``
pragma, which SQLite leaves off by default and which this schema relies on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Turn on foreign-key enforcement for SQLite connections.

    SQLite ships with foreign keys disabled for backwards compatibility. Without
    this, a bad seed or a bad request would insert dangling references and the
    board would render half-broken rows instead of failing loudly.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.sqlalchemy_url
        _engine = create_async_engine(url, echo=False, future=True)
        if url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(_engine)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,  # keep ORM objects usable after commit
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def create_all() -> None:
    """Create tables.

    `create_all` rather than Alembic on purpose: a reference slice should be
    readable end to end, and there is no historical schema to migrate from.
    ADR-0002 records what a production deployment would do instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Release pooled connections (used on shutdown and between tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
