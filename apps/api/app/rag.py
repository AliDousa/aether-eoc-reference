"""In-process retrieval over the synthetic SOP corpus in ``knowledge/``.

Okapi BM25 across heading-delimited chunks. No vector database, no embedding
service, no network call — the corpus is four Markdown files and the whole
index rebuilds in milliseconds.

Choosing lexical ranking here is a deliberate scope decision rather than a
shortcut. A reviewer can read this file, read the corpus, and verify by hand
that a cited chunk really does contain the answer. That auditability is worth
more in a reference slice than a marginal relevance gain, and it keeps the
demo runnable with no keys (ADR-0005).

``EMBEDDING_PROVIDER`` is reserved as the extension point for a hybrid dense
retriever. It is **not** implemented in this slice; the setting is documented
so the seam is visible, not so it can be claimed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

# BM25 tuning. k1 controls term-frequency saturation, b controls how strongly
# document length is normalised. These are the standard defaults; the corpus is
# far too small for tuning them to be meaningful.
_K1 = 1.5
_B = 0.75

# Terms carrying no discriminating signal in a corpus of operational protocols.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "must",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "shall",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "this",
        "to",
        "under",
        "until",
        "up",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "will",
        "with",
        "within",
        "you",
        "your",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Spelling variants folded to one form. The corpus is written in British
# English; operators type either. Lexical retrieval has no notion that these
# are the same word, so normalise at tokenisation rather than lose the match.
_NORMALISE = {
    "center": "centre",
    "centers": "centre",
    "centres": "centre",
    "litres": "litre",
    "liters": "litre",
    "liter": "litre",
    "prioritized": "priority",
    "prioritised": "priority",
    "priorities": "priority",
}


def _tokenize(text: str) -> list[str]:
    # `re.findall` is typed as list[Any]; annotating narrows it so the
    # normalisation lookup below is known to produce str, not str | None.
    raw: list[str] = _TOKEN_RE.findall(text.lower())
    return [
        _NORMALISE.get(token, token) for token in raw if token not in _STOPWORDS and len(token) > 1
    ]


def _slugify(heading: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return slug or "section"


@dataclass(frozen=True)
class Chunk:
    """One heading-delimited section of one knowledge file."""

    id: str  # "<filename>#<anchor>" — resolvable back to a file on disk
    source: str  # filename, e.g. "cooling-center-activation-checklist.md"
    anchor: str
    title: str
    text: str
    tokens: tuple[str, ...]

    @property
    def preview(self) -> str:
        collapsed = " ".join(self.text.split())
        return collapsed[:280] + ("..." if len(collapsed) > 280 else "")


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float

    def as_citation(self) -> dict[str, object]:
        return {
            "id": self.chunk.id,
            "source": self.chunk.source,
            "title": self.chunk.title,
            "anchor": self.chunk.anchor,
            "preview": self.chunk.preview,
            "score": round(self.score, 4),
        }


def _split_into_chunks(path: Path) -> list[Chunk]:
    """Split a Markdown file on level-2 headings.

    Headings are the natural retrieval unit for this corpus: each `##` section
    is one self-contained rule or checklist that can be cited on its own.
    Content before the first heading (the DEMO PROTOCOL banner and title) is
    kept as a `preamble` chunk so the disclaimer is retrievable too.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    chunks: list[Chunk] = []
    current_title = "Preamble"
    current_anchor = "preamble"
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body:
            return
        text = f"{current_title}\n{body}"
        chunks.append(
            Chunk(
                id=f"{path.name}#{current_anchor}",
                source=path.name,
                anchor=current_anchor,
                title=current_title,
                text=body,
                tokens=tuple(_tokenize(text)),
            )
        )

    for line in lines:
        if line.startswith("## "):
            flush()
            buffer = []
            current_title = line[3:].strip()
            current_anchor = _slugify(current_title)
        elif line.startswith("# ") and not chunks and not buffer:
            current_title = line[2:].strip()
            current_anchor = "preamble"
        else:
            buffer.append(line)
    flush()
    return chunks


class Corpus:
    """A BM25 index over the knowledge directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.chunks: list[Chunk] = []
        self._df: dict[str, int] = {}
        self._avg_len: float = 0.0
        self._load()

    def _load(self) -> None:
        files = sorted(self.directory.glob("*.md")) if self.directory.is_dir() else []
        self.chunks = [chunk for path in files for chunk in _split_into_chunks(path)]

        self._df = {}
        for chunk in self.chunks:
            for term in set(chunk.tokens):
                self._df[term] = self._df.get(term, 0) + 1

        lengths = [len(c.tokens) for c in self.chunks]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0

    @property
    def sources(self) -> list[str]:
        return sorted({chunk.source for chunk in self.chunks})

    def get(self, chunk_id: str) -> Chunk | None:
        return next((c for c in self.chunks if c.id == chunk_id), None)

    def _idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _score(self, chunk: Chunk, query_terms: list[str]) -> float:
        if not chunk.tokens:
            return 0.0
        doc_len = len(chunk.tokens)
        tf: dict[str, int] = {}
        for token in chunk.tokens:
            tf[token] = tf.get(token, 0) + 1

        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = self._idf(term)
            denominator = freq + _K1 * (1 - _B + _B * doc_len / (self._avg_len or 1))
            score += idf * (freq * (_K1 + 1)) / denominator

        # Heading boost: a query term appearing in the section title is a
        # stronger signal than the same term buried in a table row. Section 2 of
        # the cooling-centre checklist is literally titled "When to open a
        # SECOND cooling centre", and that should outrank a passing mention.
        title_tokens = set(_tokenize(chunk.title))
        overlap = len(title_tokens & set(query_terms))
        if overlap:
            score *= 1.0 + 0.25 * overlap

        return score

    def search(self, query: str, *, limit: int = 4, min_score: float = 0.1) -> list[Hit]:
        query_terms = _tokenize(query)
        if not query_terms or not self.chunks:
            return []
        scored = [Hit(chunk=c, score=self._score(c, query_terms)) for c in self.chunks]
        ranked = sorted((h for h in scored if h.score > min_score), key=lambda h: -h.score)
        return ranked[:limit]


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    """Process-wide index. Cleared by :func:`reload_corpus` during development."""
    return Corpus(get_settings().knowledge_dir)


def reload_corpus() -> Corpus:
    get_corpus.cache_clear()
    return get_corpus()


def search(query: str, *, limit: int = 4) -> list[Hit]:
    return get_corpus().search(query, limit=limit)


def citation_ids(hits: list[Hit]) -> list[str]:
    return [hit.chunk.id for hit in hits]


def resolve_citation(chunk_id: str) -> Chunk | None:
    """Look up a citation id. Returns None if it does not exist on disk.

    Used by the API and by the test that asserts every citation an agent emits
    is real — a cited source that cannot be opened is worse than no citation.
    """
    return get_corpus().get(chunk_id)
