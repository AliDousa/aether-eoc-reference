"""Demo authentication and ICS role-based authorisation.

This is deliberately *local-only* auth. There is no identity provider, no
password reset, no lockout, and the demo passwords are published in the README.
That is a conscious scope decision, not an oversight: wiring a reference slice
to a real agency IdP would make it unrunnable for the people it is meant to be
read by. ``docs/THREAT_MODEL.md`` states what production would require instead.

The part that *is* meant to be taken seriously is the authorisation table
below: who may commit resources is the whole point of the human-in-the-loop
story, so it lives in data and is enforced in one place.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import jwt

from app.clock import now
from app.config import get_settings
from app.enums import AgentName, IcsRole, IcsSection
from app.errors import PermissionDenied

_PBKDF2_ROUNDS = 120_000
_ALGORITHM = "HS256"

# Generated per-process when DEMO_JWT_SECRET is blank. Tokens therefore do not
# survive a restart and are worthless outside this process, which is the right
# default for something whose passwords are public.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


def _secret() -> str:
    return get_settings().demo_jwt_secret or _EPHEMERAL_SECRET


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def hash_password(password: str, *, salt: str | None = None) -> str:
    """PBKDF2-HMAC-SHA256, stored as ``pbkdf2$rounds$salt$hex``.

    Stdlib rather than passlib/bcrypt: one fewer native build for anyone
    cloning this, and the threat model does not include offline cracking of
    credentials that are printed in the README.
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, digest = encoded.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
    return hmac.compare_digest(candidate.hex(), digest)


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated operator, as carried on every request."""

    id: str
    username: str
    display_name: str
    ics_role: IcsRole
    section: IcsSection

    @property
    def label(self) -> str:
        """Role-shaped label used in audit rows and before any model call.

        Display names never reach an LLM prompt; see ``app.agents.redact``.
        """
        return self.display_name


def issue_token(user: CurrentUser) -> str:
    settings = get_settings()
    issued = now()
    payload: dict[str, Any] = {
        "sub": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "ics_role": user.ics_role.value,
        "section": user.section.value,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=settings.token_ttl_seconds)).timestamp()),
        # Marks the token as demo-issued so it can never be mistaken for one
        # minted by a real identity provider.
        "demo": True,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> CurrentUser | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    try:
        return CurrentUser(
            id=payload["sub"],
            username=payload["username"],
            display_name=payload["display_name"],
            ics_role=IcsRole(payload["ics_role"]),
            section=IcsSection(payload["section"]),
        )
    except (KeyError, ValueError):
        return None


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------


class Permission:
    """Capability names. Strings, so they read plainly in denial messages."""

    POST_ACTIVITY = "activity:post"
    CREATE_REQUEST = "request:create"
    SUBMIT_REQUEST = "request:submit"
    RUN_AGENT = "agent:run"
    DECIDE_LOGISTICS = "recommendation:decide:logistics"
    DECIDE_ANY = "recommendation:decide:any"


# Who holds which authority. Operations may run the incident log and ask the
# agents anything, but may not commit resources — that is the RBAC line the
# demo is built to show.
ROLE_PERMISSIONS: dict[IcsRole, frozenset[str]] = {
    IcsRole.INCIDENT_COMMANDER: frozenset(
        {
            Permission.POST_ACTIVITY,
            Permission.CREATE_REQUEST,
            Permission.SUBMIT_REQUEST,
            Permission.RUN_AGENT,
            Permission.DECIDE_LOGISTICS,
            Permission.DECIDE_ANY,
        }
    ),
    IcsRole.LOGISTICS_SECTION: frozenset(
        {
            Permission.POST_ACTIVITY,
            Permission.CREATE_REQUEST,
            Permission.SUBMIT_REQUEST,
            Permission.RUN_AGENT,
            Permission.DECIDE_LOGISTICS,
        }
    ),
    # In ICS the Operations Section is a *requesting* section: it raises needs
    # and logs them, and Logistics sources them. It never approves its own
    # resource movements.
    IcsRole.OPERATIONS_SECTION: frozenset(
        {
            Permission.POST_ACTIVITY,
            Permission.CREATE_REQUEST,
            Permission.SUBMIT_REQUEST,
            Permission.RUN_AGENT,
        }
    ),
    IcsRole.PLANNING_SECTION: frozenset(
        {
            Permission.POST_ACTIVITY,
            Permission.CREATE_REQUEST,
            Permission.SUBMIT_REQUEST,
            Permission.RUN_AGENT,
        }
    ),
}

# Which agents produce output inside the logistics scope. A future public-comms
# agent would not be listed here, so DECIDE_LOGISTICS alone would not clear it.
LOGISTICS_SCOPE_AGENTS: frozenset[AgentName] = frozenset({AgentName.RESOURCE_RECOMMENDER})


def permissions_for(role: IcsRole) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user: CurrentUser, permission: str) -> bool:
    return permission in permissions_for(user.ics_role)


def require(user: CurrentUser, permission: str) -> None:
    if not has_permission(user, permission):
        raise PermissionDenied(
            f"Role '{user.ics_role.value}' does not hold '{permission}'.",
            detail={"role": user.ics_role.value, "required": permission},
        )


def can_decide(user: CurrentUser, agent: AgentName) -> bool:
    """Whether this operator may accept or refuse a given agent's proposal."""
    if has_permission(user, Permission.DECIDE_ANY):
        return True
    return agent in LOGISTICS_SCOPE_AGENTS and has_permission(user, Permission.DECIDE_LOGISTICS)


def require_decision_authority(user: CurrentUser, agent: AgentName) -> None:
    if not can_decide(user, agent):
        raise PermissionDenied(
            f"Role '{user.ics_role.value}' cannot decide a '{agent.value}' recommendation. "
            "Resource movements require Incident Commander or Logistics Section authority.",
            detail={"role": user.ics_role.value, "agent": agent.value},
        )
