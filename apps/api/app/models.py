"""SQLAlchemy 2.x models.

Deliberately small and explicit. Two structural rules hold across the schema:

1. ``InventoryPosition`` is mutated in exactly one place (``app.inventory``),
   which also writes the matching ``AuditEvent``. Nothing else touches stock.
2. ``AuditEvent`` is append-only and hash-chained. There is no update path and
   no delete path anywhere in the codebase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.clock import now
from app.enums import (
    ActivityKind,
    AgentName,
    AgentRunStatus,
    IcsRole,
    IcsSection,
    IncidentStatus,
    Priority,
    RecommendationStatus,
    RequestState,
    Severity,
    SiteKind,
)
from app.types import StrEnumType


class Base(DeclarativeBase):
    # Map bare dict/list annotations onto the JSON column type so the payload
    # columns below stay readable.
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}


class Operator(Base):
    """A demo user. Never a real person: see docs/THREAT_MODEL.md."""

    __tablename__ = "operators"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    ics_role: Mapped[IcsRole] = mapped_column(StrEnumType(IcsRole, 32))
    section: Mapped[IcsSection] = mapped_column(StrEnumType(IcsSection, 32))
    # PBKDF2 over a published demo password. Stated plainly in SECURITY.md:
    # these credentials are public and must never be reused anywhere real.
    password_hash: Mapped[str] = mapped_column(String(256))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[Severity] = mapped_column(StrEnumType(Severity, 16))
    status: Mapped[IncidentStatus] = mapped_column(StrEnumType(IncidentStatus, 16))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # ICS operational period label, e.g. "OP-2".
    current_period: Mapped[str] = mapped_column(String(32))
    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    commander_operator_id: Mapped[str] = mapped_column(ForeignKey("operators.id"))
    jurisdiction: Mapped[str] = mapped_column(String(128))
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    commander: Mapped[Operator] = relationship(lazy="selectin")


class ResourceSite(Base):
    __tablename__ = "resource_sites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[SiteKind] = mapped_column(StrEnumType(SiteKind, 32))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # 1 = lowest need, 5 = highest. Drives the equity guardrail in
    # app.agents.recommender; see knowledge/resource-allocation-equity-rules.md.
    equity_priority: Mapped[int] = mapped_column(Integer, default=3)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InventoryPosition(Base):
    """Stock of one SKU at one site.

    ``on_hand`` is physical stock; ``reserved`` is committed to an approved
    request but not yet moved. Available stock is ``on_hand - reserved``, which
    is why one approval can succeed while a second for the same SKU fails.
    """

    __tablename__ = "inventory_positions"
    __table_args__ = (UniqueConstraint("site_id", "sku_id", name="uq_inventory_site_sku"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("resource_sites.id"), index=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.id"), index=True)
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    site: Mapped[ResourceSite] = relationship(lazy="selectin")
    sku: Mapped[Sku] = relationship(lazy="selectin")

    @property
    def available(self) -> int:
        return max(self.on_hand - self.reserved, 0)

    @property
    def below_reorder(self) -> bool:
        return self.available < self.reorder_point


class ResourceRequest(Base):
    __tablename__ = "resource_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    sku_id: Mapped[str] = mapped_column(ForeignKey("skus.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    priority: Mapped[Priority] = mapped_column(StrEnumType(Priority, 16), index=True)
    requesting_section: Mapped[IcsSection] = mapped_column(StrEnumType(IcsSection, 32))
    # Where the resource is needed. Null only for a draft with no destination yet.
    destination_site_id: Mapped[str | None] = mapped_column(
        ForeignKey("resource_sites.id"), nullable=True
    )
    justification: Mapped[str] = mapped_column(Text)
    state: Mapped[RequestState] = mapped_column(StrEnumType(RequestState, 24), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("operators.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    sku: Mapped[Sku] = relationship(lazy="selectin")
    destination_site: Mapped[ResourceSite | None] = relationship(lazy="selectin")
    creator: Mapped[Operator] = relationship(lazy="selectin")


class Recommendation(Base):
    """An agent proposal. Never authoritative; never mutates inventory.

    ``payload_json`` holds the structured allocation plan and
    ``equity_review_json`` the guardrail verdict that produced or blocked it.
    """

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("resource_requests.id"), index=True)
    agent: Mapped[AgentName] = mapped_column(StrEnumType(AgentName, 32))
    agent_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    equity_review_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    citations: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[RecommendationStatus] = mapped_column(
        StrEnumType(RecommendationStatus, 16), index=True
    )
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    # The plan actually approved, which may differ from payload_json when a
    # human modified it. Keeping both is the point of the exercise.
    decided_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    request: Mapped[ResourceRequest] = relationship(lazy="selectin")
    decider: Mapped[Operator | None] = relationship(lazy="selectin")


class AgentRun(Base):
    """One invocation of one agent, retained for audit.

    Stores the prompt snapshot hash rather than the prompt itself: enough to
    prove which inputs produced an output, without copying incident text into
    a second place.
    """

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    agent: Mapped[AgentName] = mapped_column(StrEnumType(AgentName, 32), index=True)
    intent: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(ForeignKey("operators.id"))
    mode: Mapped[str] = mapped_column(String(16))  # "fixture" | "llm"
    model_id: Mapped[str] = mapped_column(String(64), default="deterministic-rules-v1")
    prompt_hash: Mapped[str] = mapped_column(String(64))
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_output: Mapped[str] = mapped_column(Text, default="")
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[AgentRunStatus] = mapped_column(StrEnumType(AgentRunStatus, 24), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    requester: Mapped[Operator] = relationship(lazy="selectin")


class ActivityEvent(Base):
    """Append-only incident log: the operational narrative on the board."""

    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    kind: Mapped[ActivityKind] = mapped_column(StrEnumType(ActivityKind, 32), index=True)
    body: Mapped[str] = mapped_column(Text)
    section: Mapped[IcsSection | None] = mapped_column(StrEnumType(IcsSection, 32), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    actor: Mapped[Operator | None] = relationship(lazy="selectin")


class AuditEvent(Base):
    """Append-only, hash-chained record of every state change.

    ``prev_hash`` links each row to the one before it, so altering or removing
    a historical row breaks verification for every subsequent row. There is no
    ORM update or delete path for this table anywhere in the codebase; see
    ADR-0004 and ``GET /api/audit/verify``.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_action_at", "action", "at"),)

    # Monotonic chain position. Autoincrement rather than a random id because
    # verification depends on a total order.
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    actor_label: Mapped[str] = mapped_column(String(64), default="system")
    # Dotted action namespace: request.*, inventory.*, ai.*, auth.*
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(32), index=True)
    ai_trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
