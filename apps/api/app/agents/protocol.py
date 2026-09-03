"""Protocol Retriever (RAG).

Answers protocol questions from the bundled synthetic SOP corpus and nothing
else. If retrieval finds nothing above threshold, it says so instead of
answering from parametric knowledge — a confident answer with no source is the
single most dangerous output an EOC assistant can produce.

Every answer carries the verify banner and citations that resolve to a real
chunk on disk.
"""

from __future__ import annotations

from typing import Any

from app import rag
from app.agents import llm
from app.agents.base import VERIFY_BANNER, AgentResult
from app.agents.redact import RedactionMap
from app.enums import AgentName, AgentRunStatus

_SYSTEM_PROMPT = (
    "You answer questions about emergency-operations protocols using ONLY the "
    "excerpts provided. Quote thresholds and numbers exactly as written. If the "
    "excerpts do not contain the answer, say so plainly and do not substitute "
    "general knowledge. Never give clinical advice. Cite the excerpt ids you "
    "used, in square brackets."
)

_NO_ANSWER = (
    "The bundled protocol corpus does not cover this question. No answer is given "
    "rather than guessing. Rephrase the question, or consult current official "
    "guidance directly."
)


def _extractive_answer(question: str, hits: list[rag.Hit]) -> str:
    """Compose an answer from the retrieved text itself.

    Extractive rather than generative on the no-model path: the corpus already
    contains the thresholds in plain language, and quoting them is both more
    accurate and more checkable than paraphrasing.
    """
    lines = [f"Answering from {len(hits)} protocol section(s):", ""]
    for hit in hits:
        chunk = hit.chunk
        body = "\n".join(
            line for line in chunk.text.splitlines() if line.strip() and not line.startswith(">")
        )
        lines.append(f"### {chunk.title}")
        lines.append(f"_Source: `{chunk.id}`_")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).strip()


async def run(question: str, *, mapping: RedactionMap | None = None) -> AgentResult:
    hits = rag.search(question, limit=3)

    if not hits:
        return AgentResult(
            agent=AgentName.PROTOCOL_RETRIEVER,
            intent="protocol_question",
            summary=_NO_ANSWER,
            structured={"question": question, "answered": False, "chunks": []},
            citations=[],
            confidence=0.0,
            uncertainty=["No section of the bundled corpus matched this question."],
            mode="fixture",
            raw_output=_NO_ANSWER,
            requires_human=False,
            status=AgentRunStatus.COMPLETE,
        )

    answer = _extractive_answer(question, hits)
    mode = "fixture"
    model_id = "deterministic-rules-v1"
    prompt_hash = ""

    if llm.is_enabled():
        excerpts = "\n\n".join(f"[{hit.chunk.id}]\n{hit.chunk.text}" for hit in hits)
        user_prompt = f"Question: {question}\n\nExcerpts:\n{excerpts}"
        prompt_hash = llm.prompt_hash(user_prompt)
        result = await llm.complete(system=_SYSTEM_PROMPT, user=user_prompt, mapping=mapping)
        if result.ok:
            answer = result.text
            mode = "llm"
            model_id = result.model_id

    citations = [hit.as_citation() for hit in hits]
    top_score = hits[0].score
    # Retrieval score is a weak proxy for confidence; cap it low enough that
    # nobody reads this as authoritative.
    confidence = max(0.35, min(0.8, top_score / 12.0))

    structured: dict[str, Any] = {
        "question": question,
        "answered": True,
        "banner": VERIFY_BANNER,
        "chunks": [
            {"id": hit.chunk.id, "title": hit.chunk.title, "score": round(hit.score, 3)}
            for hit in hits
        ],
    }

    return AgentResult(
        agent=AgentName.PROTOCOL_RETRIEVER,
        intent="protocol_question",
        summary=answer,
        structured=structured,
        citations=citations,
        confidence=confidence,
        uncertainty=[
            "Answered only from the bundled synthetic corpus, which is a demo artefact "
            "and not official guidance.",
            "The corpus has no revision date and is not synchronised with any authority.",
        ],
        mode=mode,
        model_id=model_id,
        prompt_hash=prompt_hash,
        raw_output=answer,
        requires_human=False,
        status=AgentRunStatus.COMPLETE,
    )
