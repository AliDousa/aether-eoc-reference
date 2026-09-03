"""Agent invocation and run history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app import board
from app import requests as requests_service
from app.agents import supervisor
from app.agents.base import VERIFY_BANNER
from app.config import get_settings
from app.deps import CorrelationDep, CurrentUserDep, DbSession
from app.enums import AgentName
from app.errors import NotFound
from app.models import AgentRun
from app.schemas import AgentRunBody
from app.security import Permission, require

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Static descriptions rendered on the Agents page. Kept beside the code they
# describe so a change in behaviour is visible next to its own claim.
AGENT_CATALOGUE: list[dict[str, Any]] = [
    {
        "name": AgentName.SITUATION_ASSESSMENT.value,
        "label": "Situation Assessment",
        "intent": "situation_summary",
        "purpose": "Summarise the incident and recent activity in SITREP shape.",
        "will": [
            "Cite the activity events it read",
            "State information gaps explicitly, always",
        ],
        "will_not": [
            "Move resources",
            "Give clinical advice",
            "Report an objective as met without evidence",
        ],
        "requires_human": False,
    },
    {
        "name": AgentName.PROTOCOL_RETRIEVER.value,
        "label": "Protocol Retriever",
        "intent": "protocol_question",
        "purpose": "Answer protocol questions from the bundled synthetic SOP corpus only.",
        "will": [
            "Quote thresholds exactly as written",
            "Cite chunk ids that resolve on disk",
            "Say it does not know when retrieval finds nothing",
        ],
        "will_not": [
            "Answer from general knowledge",
            "Give clinical advice",
            "Claim official authority",
        ],
        "requires_human": False,
    },
    {
        "name": AgentName.RESOURCE_RECOMMENDER.value,
        "label": "Resource Recommender",
        "intent": "resource_recommendation",
        "purpose": "Propose a multi-site allocation that respects the equity floor.",
        "will": [
            "State shortfalls explicitly",
            "Show which sites were considered and what was withheld",
            "Stop before execution, always",
        ],
        "will_not": [
            "Write inventory",
            "Zero out a high-need site",
            "Override the equity floor (only an Incident Commander may)",
        ],
        "requires_human": True,
    },
]


@router.get("")
async def catalogue(session: DbSession) -> dict[str, Any]:
    """Agent roster, current mode, and knowledge sources."""
    settings = get_settings()
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(10)
    runs = list((await session.execute(stmt)).scalars())

    return {
        "agents": AGENT_CATALOGUE,
        "mode": "llm" if settings.llm_enabled else "fixture",
        "llm_enabled": settings.llm_enabled,
        "model_id": settings.llm_model if settings.llm_enabled else "deterministic-rules-v1",
        "banner": VERIFY_BANNER,
        "knowledge_sources": supervisor.available_sources(),
        "recent_runs": [supervisor.serialize_run(run) for run in runs],
    }


@router.get("/runs")
async def runs(
    session: DbSession,
    limit: int = Query(default=25, ge=1, le=200),
    agent: str | None = None,
) -> dict[str, Any]:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if agent:
        stmt = stmt.where(AgentRun.agent == agent)
    return {
        "runs": [supervisor.serialize_run(run) for run in (await session.execute(stmt)).scalars()]
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, session: DbSession) -> dict[str, Any]:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFound(f"Unknown agent run '{run_id}'.")
    return {"run": supervisor.serialize_run(run)}


@router.post("/run")
async def run_agent(
    body: AgentRunBody,
    session: DbSession,
    user: CurrentUserDep,
    correlation_id: CorrelationDep,
) -> dict[str, Any]:
    """Route one intent through the supervisor.

    Any output that could move resources comes back with status
    ``awaiting_human`` and a pending recommendation attached. Nothing here can
    reach ``app.inventory``.
    """
    require(user, Permission.RUN_AGENT)
    incident = await board.current_incident(session)
    if incident is None:
        raise NotFound("No incident has been seeded. Run `make seed`.")

    run, result, recommendation = await supervisor.run_intent(
        session,
        incident_id=incident.id,
        intent=body.intent,
        actor=user,
        correlation_id=correlation_id,
        question=body.question,
        request_id=body.request_id,
    )
    await session.commit()

    payload: dict[str, Any] = {
        "run": supervisor.serialize_run(run),
        "result": result.as_payload(),
    }
    if recommendation is not None:
        payload["recommendation"] = requests_service.serialize_recommendation(recommendation)
    return payload
