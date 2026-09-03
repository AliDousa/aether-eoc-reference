"""Retrieval honesty and the authentication boundary."""

from __future__ import annotations

import httpx

from app import rag
from app.config import get_settings
from conftest import auth, login


def test_every_citation_resolves_to_a_real_chunk_on_disk() -> None:
    """A citation that cannot be opened is worse than no citation."""
    corpus = rag.get_corpus()
    assert corpus.chunks, "The knowledge corpus should not be empty."

    knowledge_dir = get_settings().knowledge_dir
    for query in [
        "When do we open a second cooling center?",
        "how much ORS per occupant",
        "equity floor allocation",
        "what must a sitrep say about uncertainty",
    ]:
        hits = rag.search(query, limit=3)
        assert hits, f"No retrieval hits for: {query}"
        for hit in hits:
            chunk_id = hit.chunk.id
            # The id resolves through the public API...
            assert rag.resolve_citation(chunk_id) is not None
            # ...and its source file genuinely exists on disk.
            source, _, anchor = chunk_id.partition("#")
            assert (knowledge_dir / source).is_file(), f"Missing source file: {source}"
            assert anchor, "A citation must point at a section, not a whole file."


def test_unknown_citation_does_not_resolve() -> None:
    assert rag.resolve_citation("not-a-real-file.md#nope") is None


def test_retrieval_finds_the_cooling_centre_threshold() -> None:
    """The demo script's question must land on the section that answers it."""
    hits = rag.search("When do we open a second cooling center?", limit=3)
    top = hits[0].chunk
    assert top.source == "cooling-center-activation-checklist.md"
    assert "second cooling centre" in top.title.lower()
    # The answer text carries the actual thresholds, not a paraphrase.
    assert "80 %" in top.text or "80%" in top.text


async def test_agent_output_cites_only_real_sources(client: httpx.AsyncClient) -> None:
    token = await login(client, "ic.demo")
    response = await client.post(
        "/api/agents/run",
        headers=auth(token),
        json={
            "intent": "protocol_question",
            "question": "When do we open a second cooling center?",
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]

    assert result["banner"].startswith("AI-suggested")
    assert result["citations"], "A protocol answer must cite its sources."
    for citation in result["citations"]:
        assert rag.resolve_citation(citation["id"]) is not None
    # The retriever must state its limits.
    assert result["uncertainty"]


async def test_unauthenticated_writes_are_rejected(client: httpx.AsyncClient) -> None:
    """Every mutating endpoint requires a bearer token."""
    board = (await client.get("/api/incidents/current")).json()
    incident_id = board["incident"]["id"]
    request_id = board["requests"][0]["id"]

    unauthenticated = [
        ("POST", f"/api/incidents/{incident_id}/activity", {"body": "should not be written"}),
        (
            "POST",
            "/api/requests",
            {
                "sku_id": "sku_ors",
                "quantity": 10,
                "priority": "routine",
                "requesting_section": "operations",
                "destination_site_id": "site_north",
                "justification": "should not be written",
            },
        ),
        ("POST", f"/api/requests/{request_id}/transition", {"target": "cancelled"}),
        ("POST", f"/api/requests/{request_id}/recommend", None),
        ("POST", "/api/agents/run", {"intent": "situation_summary"}),
        ("POST", "/api/recommendations/rec_missing/decide", {"decision": "approve"}),
    ]

    for method, path, body in unauthenticated:
        response = await client.request(method, path, json=body)
        assert response.status_code == 401, f"{path} accepted an unauthenticated write"
        assert response.headers.get("www-authenticate") == "Bearer"

    # A malformed token is rejected the same way.
    response = await client.post(
        f"/api/incidents/{incident_id}/activity",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"body": "nope"},
    )
    assert response.status_code == 401


async def test_reads_stay_open_for_review(client: httpx.AsyncClient) -> None:
    """The board is readable without a token; only writes are gated."""
    for path in ["/api/health", "/api/incidents/current", "/api/audit/verify", "/api/knowledge"]:
        assert (await client.get(path)).status_code == 200


async def test_knowledge_endpoint_rejects_path_traversal(client: httpx.AsyncClient) -> None:
    for attempt in ["../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "notes.txt"]:
        response = await client.get(f"/api/knowledge/{attempt}")
        assert response.status_code == 404
