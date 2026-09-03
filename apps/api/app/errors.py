"""Domain errors.

Raised by the service layer and translated to HTTP once, in ``app.main``, so
that service functions stay usable from the seeder and the tests without
importing FastAPI.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, caller-fixable failures."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class IllegalTransition(DomainError):
    """A resource request was pushed into a state it cannot reach from here."""

    status_code = 409
    code = "illegal_transition"


class InsufficientStock(DomainError):
    """A movement would drive available stock below zero."""

    status_code = 409
    code = "insufficient_stock"


class EquityGuardrailViolation(DomainError):
    """An allocation would zero out a high-need site. Fails closed."""

    status_code = 409
    code = "equity_guardrail"


class PermissionDenied(DomainError):
    """The actor's ICS role does not carry this authority."""

    status_code = 403
    code = "permission_denied"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"
