"""Resource-request lifecycle.

The legal transitions live in one table rather than scattered across handlers,
because the difference between a workflow engine you can reason about and a
legacy EOC board you cannot is usually just this: whether the rules are stated
once, in data, or implied by a hundred conditionals.

    draft -> submitted -> recommended -> approved | modified | rejected
                                              |        |
                                              +--------+--> tasked -> fulfilled

``cancelled`` is reachable from any non-terminal state. ``rejected``,
``fulfilled`` and ``cancelled`` are terminal.
"""

from __future__ import annotations

from app.enums import RequestState
from app.errors import IllegalTransition

LEGAL_TRANSITIONS: dict[RequestState, frozenset[RequestState]] = {
    RequestState.DRAFT: frozenset({RequestState.SUBMITTED, RequestState.CANCELLED}),
    RequestState.SUBMITTED: frozenset({RequestState.RECOMMENDED, RequestState.CANCELLED}),
    # A recommendation exists; a human now approves, edits, or refuses it.
    RequestState.RECOMMENDED: frozenset(
        {
            RequestState.APPROVED,
            RequestState.MODIFIED,
            RequestState.REJECTED,
            RequestState.CANCELLED,
        }
    ),
    RequestState.APPROVED: frozenset({RequestState.TASKED, RequestState.CANCELLED}),
    RequestState.MODIFIED: frozenset({RequestState.TASKED, RequestState.CANCELLED}),
    RequestState.TASKED: frozenset({RequestState.FULFILLED, RequestState.CANCELLED}),
    # Terminal states.
    RequestState.REJECTED: frozenset(),
    RequestState.FULFILLED: frozenset(),
    RequestState.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[RequestState] = frozenset(
    state for state, targets in LEGAL_TRANSITIONS.items() if not targets
)

# States in which stock has been committed by a human decision. Used by the
# board KPIs and by the guard in app.inventory.
COMMITTED_STATES: frozenset[RequestState] = frozenset(
    {RequestState.APPROVED, RequestState.MODIFIED, RequestState.TASKED, RequestState.FULFILLED}
)


def allowed_transitions(current: RequestState) -> frozenset[RequestState]:
    return LEGAL_TRANSITIONS.get(current, frozenset())


def can_transition(current: RequestState, target: RequestState) -> bool:
    return target in allowed_transitions(current)


def assert_transition(current: RequestState, target: RequestState) -> None:
    """Raise :class:`IllegalTransition` unless the move is legal.

    Callers get the permitted set back in the error detail so a UI can render
    the real options instead of guessing.
    """
    if not can_transition(current, target):
        allowed = sorted(s.value for s in allowed_transitions(current))
        raise IllegalTransition(
            f"Cannot move a request from '{current.value}' to '{target.value}'.",
            detail={"from": current.value, "to": target.value, "allowed": allowed},
        )
