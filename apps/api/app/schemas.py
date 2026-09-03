"""Pydantic models for the HTTP boundary.

Request bodies are validated here so handlers receive typed values, and the
constraints (quantity must be positive, a rejection must carry a reason) are
declared once and appear in the OpenAPI schema at ``/api/docs``.

Responses are mostly serialised by the service layer, which already produces
the exact JSON the UI consumes; duplicating those shapes as response models
would add a second place to keep in sync for no validation benefit. The
response models defined here are the ones with a fixed, small shape worth
documenting.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import IcsSection, Priority, RequestState


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class DemoOperator(BaseModel):
    """A seeded login, listed on the sign-in screen."""

    username: str
    display_name: str
    ics_role: str
    section: str
    advertised: bool


class LoginResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    operator: dict[str, Any]
    permissions: list[str]
    demo_mode: bool


class ActivityNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=2000)
    section: IcsSection | None = None


class CreateRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: str = Field(min_length=1, max_length=32)
    quantity: int = Field(gt=0, le=100_000)
    priority: Priority
    requesting_section: IcsSection
    destination_site_id: str = Field(min_length=1, max_length=32)
    justification: str = Field(min_length=1, max_length=2000)


class TransitionRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: RequestState
    note: str = Field(default="", max_length=500)


class AllocationLeg(BaseModel):
    """One leg of a (possibly human-edited) allocation."""

    model_config = ConfigDict(extra="forbid")

    from_site_id: str = Field(min_length=1, max_length=32)
    from_site_name: str = Field(default="", max_length=128)
    quantity: int = Field(gt=0, le=100_000)
    equity_priority: int = Field(default=3, ge=1, le=5)


class DecisionBody(BaseModel):
    """A human decision on a recommendation.

    ``modified_legs`` is what makes "modify then approve" distinct from
    "approve": supplying it records the decision as ``modified`` and re-runs
    the equity check against the edited plan.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "modify", "reject"]
    reason: str = Field(default="", max_length=1000)
    modified_legs: list[AllocationLeg] | None = None
    # Only an Incident Commander may set this, and only with a reason.
    override_equity: bool = False


class AgentRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["situation_summary", "protocol_question", "resource_recommendation"]
    question: str | None = Field(default=None, max_length=1000)
    request_id: str | None = Field(default=None, max_length=32)


class ChainVerificationResponse(BaseModel):
    ok: bool
    checked: int
    head_hash: str
    genesis_hash: str
    broken_at_seq: int | None = None
    detail: str
    problems: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    demo_mode: bool
    llm_enabled: bool
    agent_mode: Literal["fixture", "llm"]
    knowledge_sources: int
    incident: str | None
