"""The request lifecycle must refuse moves that are not on the map."""

from __future__ import annotations

from itertools import pairwise

import httpx
import pytest

from app.enums import RequestState
from app.errors import IllegalTransition
from app.state_machine import TERMINAL_STATES, allowed_transitions, assert_transition
from conftest import auth, immediate_request, login


def test_illegal_transitions_are_rejected() -> None:
    # A submitted request has no recommendation yet, so it cannot be approved.
    with pytest.raises(IllegalTransition) as excinfo:
        assert_transition(RequestState.SUBMITTED, RequestState.APPROVED)
    assert "submitted" in str(excinfo.value)
    # The error carries the permitted set so a client never has to guess.
    assert excinfo.value.detail["allowed"] == ["cancelled", "recommended"]

    # Terminal states go nowhere at all.
    for terminal in TERMINAL_STATES:
        assert allowed_transitions(terminal) == frozenset()
        with pytest.raises(IllegalTransition):
            assert_transition(terminal, RequestState.SUBMITTED)

    # And a request cannot skip the human decision entirely.
    with pytest.raises(IllegalTransition):
        assert_transition(RequestState.SUBMITTED, RequestState.FULFILLED)


def test_legal_path_is_walkable() -> None:
    path = [
        RequestState.DRAFT,
        RequestState.SUBMITTED,
        RequestState.RECOMMENDED,
        RequestState.APPROVED,
        RequestState.TASKED,
        RequestState.FULFILLED,
    ]
    for current, target in pairwise(path):
        assert_transition(current, target)  # must not raise


async def test_api_rejects_illegal_transition_with_409(client: httpx.AsyncClient) -> None:
    token = await login(client, "logistics.demo")
    request = await immediate_request(client)

    response = await client.post(
        f"/api/requests/{request['id']}/transition",
        headers=auth(token),
        json={"target": "fulfilled", "note": "skipping the queue"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "illegal_transition"
    assert body["detail"]["from"] == "submitted"
    assert "recommended" in body["detail"]["allowed"]
