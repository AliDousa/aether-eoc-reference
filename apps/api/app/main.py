"""FastAPI application entrypoint.

One process serves the REST API and the WebSocket (ADR-0001, ADR-0003).
Interactive OpenAPI is at ``/api/docs``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import rag
from app.config import get_settings
from app.db import create_all, dispose_engine, get_session_factory
from app.errors import DomainError
from app.models import Incident
from app.routers import agents, audit, auth, incidents, inventory, knowledge, requests, ws
from app.schemas import HealthResponse

DESCRIPTION = """
Reference slice of a next-generation public-health Emergency Operations Center.

**This is a demonstration.** All data is synthetic. There are no production
integrations, no patient data, and no live incident feeds.

Three things are worth looking at:

* `POST /api/recommendations/{id}/decide` — the only route from an AI proposal
  to a stock movement, and it requires a human with ICS authority.
* `GET /api/audit/verify` — replays the hash-chained audit log from genesis.
* `POST /api/agents/run` — the supervisor. With `LLM_PROVIDER=none` every agent
  runs deterministically and the whole demo works offline.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # create_all rather than migrations: there is no historical schema to
    # migrate from in a reference slice (ADR-0002).
    await create_all()
    rag.get_corpus()  # build the retrieval index once at startup
    yield
    await dispose_engine()


app = FastAPI(
    title="Aether EOC Reference API",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # bearer tokens, not cookies (see app.deps)
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Translate service-layer errors to HTTP in one place.

    Service functions stay importable from the seeder and the tests without
    depending on FastAPI, and every error reaches the client in one shape.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


app.include_router(auth.router)
app.include_router(incidents.router)
app.include_router(requests.router)
app.include_router(inventory.router)
app.include_router(audit.router)
app.include_router(agents.router)
app.include_router(knowledge.router)
app.include_router(ws.router)


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness plus the two facts a reviewer most often wants to confirm:
    whether this is demo mode, and whether the agents are using a model."""
    factory = get_session_factory()
    async with factory() as session:
        incident = (
            await session.execute(select(Incident).order_by(Incident.activated_at.desc()).limit(1))
        ).scalar_one_or_none()

    return HealthResponse(
        status="ok",
        demo_mode=settings.demo_mode,
        llm_enabled=settings.llm_enabled,
        agent_mode="llm" if settings.llm_enabled else "fixture",
        knowledge_sources=len(rag.get_corpus().sources),
        incident=incident.name if incident else None,
    )


@app.get("/", tags=["meta"])
async def root() -> dict[str, Any]:
    return {
        "name": "Aether EOC Reference API",
        "notice": "SYNTHETIC DEMO — not a live EOC. All data is fictional.",
        "docs": "/api/docs",
        "board": "/api/incidents/current",
        "audit_verify": "/api/audit/verify",
    }
