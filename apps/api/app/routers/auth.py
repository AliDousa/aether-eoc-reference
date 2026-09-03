"""Demo authentication endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import audit
from app.config import get_settings
from app.deps import CorrelationDep, CurrentUserDep, DbSession
from app.enums import IcsRole, IcsSection
from app.models import Operator
from app.schemas import DemoOperator, LoginRequest, LoginResponse
from app.security import CurrentUser, issue_token, permissions_for, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _operator_payload(operator: Operator) -> dict[str, object]:
    return {
        "id": operator.id,
        "username": operator.username,
        "display_name": operator.display_name,
        "ics_role": str(operator.ics_role),
        "section": str(operator.section),
    }


@router.get("/demo-operators", response_model=list[DemoOperator])
async def demo_operators(session: DbSession) -> list[DemoOperator]:
    """List the seeded logins.

    Exposed so the sign-in screen can offer one-click login. Safe only because
    every account here is synthetic and the password is published; guarded by
    DEMO_MODE so a non-demo deployment cannot enumerate its users.
    """
    if not get_settings().demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Demo operators are not exposed."},
        )

    advertised = _advertised_usernames()
    operators = list((await session.execute(select(Operator))).scalars())
    return [
        DemoOperator(
            username=operator.username,
            display_name=operator.display_name,
            ics_role=str(operator.ics_role),
            section=str(operator.section),
            advertised=operator.username in advertised,
        )
        for operator in operators
    ]


def _advertised_usernames() -> set[str]:
    """The three logins the README documents, marked for prominence."""
    path = get_settings().fixtures_dir / "operators.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["username"] for row in data.get("operators", []) if row.get("advertised")}


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: DbSession,
    correlation_id: CorrelationDep,
) -> LoginResponse:
    stmt = select(Operator).where(Operator.username == body.username.strip().lower())
    operator = (await session.execute(stmt)).scalar_one_or_none()

    # Same response whether the account is missing or the password is wrong.
    if operator is None or not verify_password(body.password, operator.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Unknown username or password."},
        )

    user = CurrentUser(
        id=operator.id,
        username=operator.username,
        display_name=operator.display_name,
        ics_role=IcsRole(operator.ics_role),
        section=IcsSection(operator.section),
    )

    await audit.record(
        session,
        action="auth.login",
        entity_type="operator",
        entity_id=operator.id,
        correlation_id=correlation_id,
        actor_id=operator.id,
        actor_label=operator.display_name,
        after={"username": operator.username, "ics_role": str(operator.ics_role)},
    )
    await session.commit()

    return LoginResponse(
        token=issue_token(user),
        operator=_operator_payload(operator),
        permissions=sorted(permissions_for(user.ics_role)),
        demo_mode=get_settings().demo_mode,
    )


@router.get("/me")
async def me(user: CurrentUserDep) -> dict[str, object]:
    return {
        "operator": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "ics_role": user.ics_role.value,
            "section": user.section.value,
        },
        "permissions": sorted(permissions_for(user.ics_role)),
        "demo_mode": get_settings().demo_mode,
    }
