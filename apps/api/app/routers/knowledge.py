"""The synthetic SOP corpus, browsable and searchable.

Exposed so a reviewer can check a citation by hand: an agent claims a threshold,
you open the cited chunk, and you see whether it says that. A citation you
cannot open is decoration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app import rag
from app.config import get_settings
from app.errors import NotFound

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

DEMO_NOTICE = "DEMO PROTOCOL — not official guidance. For software demonstration only."


@router.get("")
async def list_sources() -> dict[str, Any]:
    corpus = rag.get_corpus()
    by_source: dict[str, list[dict[str, Any]]] = {}
    for chunk in corpus.chunks:
        by_source.setdefault(chunk.source, []).append(
            {"id": chunk.id, "title": chunk.title, "anchor": chunk.anchor}
        )
    return {
        "notice": DEMO_NOTICE,
        "sources": [
            {"source": source, "sections": sections, "section_count": len(sections)}
            for source, sections in sorted(by_source.items())
        ],
        "chunk_count": len(corpus.chunks),
    }


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    hits = rag.search(q, limit=limit)
    return {
        "notice": DEMO_NOTICE,
        "query": q,
        "hits": [hit.as_citation() for hit in hits],
    }


@router.get("/chunk")
async def get_chunk(id: str = Query(min_length=1, max_length=300)) -> dict[str, Any]:
    """Resolve one citation id to its full text."""
    chunk = rag.resolve_citation(id)
    if chunk is None:
        raise NotFound(f"Unknown knowledge chunk '{id}'.")
    return {
        "notice": DEMO_NOTICE,
        "chunk": {
            "id": chunk.id,
            "source": chunk.source,
            "anchor": chunk.anchor,
            "title": chunk.title,
            "text": chunk.text,
        },
    }


@router.get("/{source}")
async def get_source(source: str) -> dict[str, Any]:
    """Full text of one knowledge file."""
    settings = get_settings()
    # Reject anything that is not a bare filename: this handler joins user
    # input to a directory, so traversal is the obvious risk to close.
    if "/" in source or "\\" in source or not source.endswith(".md"):
        raise NotFound(f"Unknown knowledge source '{source}'.")

    path = settings.knowledge_dir / source
    if not path.is_file() or path.parent.resolve() != settings.knowledge_dir.resolve():
        raise NotFound(f"Unknown knowledge source '{source}'.")

    corpus = rag.get_corpus()
    return {
        "notice": DEMO_NOTICE,
        "source": source,
        "text": path.read_text(encoding="utf-8"),
        "sections": [
            {"id": chunk.id, "title": chunk.title, "anchor": chunk.anchor}
            for chunk in corpus.chunks
            if chunk.source == source
        ],
    }
