"""Domain vocabulary.

These are `StrEnum` so they serialise as plain strings in JSON, SQLite, audit
payloads, and WebSocket frames without a custom encoder — one spelling of each
value everywhere it appears.
"""

from __future__ import annotations

from enum import StrEnum


class IcsSection(StrEnum):
    """ICS general staff sections. Finance/Admin is present but read-only here."""

    COMMAND = "command"
    OPERATIONS = "operations"
    PLANNING = "planning"
    LOGISTICS = "logistics"
    FINANCE_ADMIN = "finance_admin"


class IcsRole(StrEnum):
    INCIDENT_COMMANDER = "incident_commander"
    OPERATIONS_SECTION = "operations_section"
    LOGISTICS_SECTION = "logistics_section"
    PLANNING_SECTION = "planning_section"


class IncidentStatus(StrEnum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    DEMOBILIZING = "demobilizing"
    CLOSED = "closed"


class Severity(StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"


class SiteKind(StrEnum):
    WAREHOUSE = "warehouse"
    COOLING_CENTER = "cooling_center"
    CLINIC = "clinic"
    FIELD_TEAM = "field_team"


class Priority(StrEnum):
    """ICS resource-request precedence, most urgent last for ordering clarity."""

    ROUTINE = "routine"
    PRIORITY = "priority"
    IMMEDIATE = "immediate"

    @property
    def rank(self) -> int:
        return {"routine": 0, "priority": 1, "immediate": 2}[self.value]


class RequestState(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"
    TASKED = "tasked"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class RecommendationStatus(StrEnum):
    """`PENDING` is the human-in-the-loop hold: nothing has been actioned."""

    PENDING = "pending"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"


class AgentName(StrEnum):
    SUPERVISOR = "supervisor"
    SITUATION_ASSESSMENT = "situation_assessment"
    PROTOCOL_RETRIEVER = "protocol_retriever"
    RESOURCE_RECOMMENDER = "resource_recommender"


class AgentRunStatus(StrEnum):
    """`AWAITING_HUMAN` marks output that could change resources or comms.

    Advisory output (a summary, a cited protocol answer) completes on its own;
    anything that would move stock stops here until a human decides.
    """

    COMPLETE = "complete"
    AWAITING_HUMAN = "awaiting_human"
    FAILED = "failed"


class ActivityKind(StrEnum):
    LOG_NOTE = "log_note"
    STATUS_CHANGE = "status_change"
    RESOURCE_REQUEST = "resource_request"
    RESOURCE_MOVEMENT = "resource_movement"
    AGENT_OUTPUT = "agent_output"
    HUMAN_DECISION = "human_decision"
