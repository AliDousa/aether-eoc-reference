"""FastAPI dependencies.

Authentication is a bearer token in the ``Authorization`` header rather than a
cookie. The web app runs on a different origin from the API in the default
local setup, and a cross-origin cookie would need ``SameSite=None; Secure``,
which does not work over plain HTTP on localhost. A demo that requires TLS to
log in is a demo nobody runs.

The cost is that the token lives in browser storage and is therefore exposed to
XSS. That is acceptable for a synthetic demo whose passwords are printed in the
README, and unacceptable in production — ``docs/THREAT_MODEL.md`` says so
explicitly rather than leaving the reader to notice.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.ids import correlation_id as new_correlation_id
from app.security import CurrentUser, decode_token

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthenticated", "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve the caller, or reject with 401.

    Every write endpoint depends on this, which is what makes the
    "unauthenticated write is rejected" guarantee structural rather than
    per-handler.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Provide a bearer token. POST /api/auth/login to get one.")

    user = decode_token(authorization.split(" ", 1)[1].strip())
    if user is None:
        raise _unauthorized("Token is invalid or expired.")
    return user


async def optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """Resolve the caller if a valid token is present, else None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return decode_token(authorization.split(" ", 1)[1].strip())


def correlation_id(
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> str:
    """Correlation id for this request.

    Honours a client-supplied ``X-Correlation-Id`` so a UI action that causes
    several writes ties them together in the audit log; otherwise generates one.
    """
    return (x_correlation_id or "").strip()[:32] or new_correlation_id()


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(optional_user)]
CorrelationDep = Annotated[str, Depends(correlation_id)]
