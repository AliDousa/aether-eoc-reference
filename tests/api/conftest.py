"""Shared fixtures for the API tests.

Every test runs against a freshly seeded, throwaway SQLite file. That is slower
than sharing one database, and worth it: these tests assert things about
*counts* — one inventory mutation, two audit rows — which silently stop meaning
anything if state leaks between tests.

The environment is configured before any `app.*` import because settings are
cached with `lru_cache`.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Point the app at a scratch database and force fixture mode before import.
_TMP = Path(tempfile.mkdtemp(prefix="aether-eoc-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_PROVIDER"] = "none"
os.environ["DEMO_MODE"] = "true"
# Stable secret so tokens survive within a test run.
os.environ["DEMO_JWT_SECRET"] = "test-secret-not-used-anywhere-real"
os.environ["KNOWLEDGE_DIR"] = str(REPO_ROOT / "knowledge")
os.environ["FIXTURES_DIR"] = str(REPO_ROOT / "fixtures")

import httpx  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app import seed as seeder  # noqa: E402
from app.db import dispose_engine, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_database() -> AsyncIterator[None]:
    """Rebuild the scenario before each test, then drop the connection pool."""
    # A unique file per test: reusing one path can collide with a pooled
    # connection that has not closed yet on Windows.
    os.environ["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{(_TMP / f'test-{uuid.uuid4().hex}.db').as_posix()}"
    )
    from app.config import get_settings

    get_settings.cache_clear()
    await dispose_engine()

    await seeder.main(reset=True, quiet=True)
    yield
    await dispose_engine()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as db:
        yield db


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as http:
        yield http


async def login(http: httpx.AsyncClient, username: str) -> str:
    """Return a bearer token for a seeded demo operator."""
    response = await http.post(
        "/api/auth/login", json={"username": username, "password": "demo"}
    )
    response.raise_for_status()
    return str(response.json()["token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def immediate_request(http: httpx.AsyncClient) -> dict:
    """The seeded IMMEDIATE ORS request — the one that cannot be filled."""
    board = (await http.get("/api/incidents/current")).json()
    for request in board["requests"]:
        if request["priority"] == "immediate" and request["state"] == "submitted":
            return request
    raise AssertionError("The seeded scenario is missing its open IMMEDIATE request.")
