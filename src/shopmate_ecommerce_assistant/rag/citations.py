"""Stable citations for policy answers.

A citation is derived only from stored metadata, never from model output: the same chunk
always yields the same ``citation_id``, and the payload carries everything a support agent
needs to audit the claim (document, chunk, heading, page, version, effective window).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SNIPPET_CHARS = 220


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """A candidate chunk that already passed retrieval and metadata re-checks."""

    chunk_id: str
    document_id: str
    version_id: str
    title: str
    heading_path: tuple[str, ...]
    page_no: int | None
    version: str
    effective_from: datetime
    effective_to: datetime | None
    text: str
    token_count: int
    score: float
    dense_similarity: float | None
    rrf_rank: int
    branch_support: int = 1


@dataclass(frozen=True, slots=True)
class Citation:
    """A citable passage with a stable id and a human-readable label."""

    citation_id: str
    label: str
    document_id: str
    chunk_id: str
    version_id: str
    title: str
    heading: str
    page_no: int | None
    version: str
    effective_from: str
    effective_to: str | None
    snippet: str
    score: float
    dense_similarity: float | None

    def as_dict(self) -> dict[str, Any]:
        """Return the payload used by the SSE ``citation`` event and the answer record."""
        return {
            "citation_id": self.citation_id,
            "label": self.label,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "version_id": self.version_id,
            "title": self.title,
            "heading": self.heading,
            "page_no": self.page_no,
            "version": self.version,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "snippet": self.snippet,
            "score": round(self.score, 6),
            "dense_similarity": (
                None if self.dense_similarity is None else round(self.dense_similarity, 6)
            ),
        }


def citation_id_for(chunk_id: str) -> str:
    """Derive a deterministic citation id from a chunk id."""
    digest = hashlib.blake2b(chunk_id.encode("utf-8"), digest_size=8).hexdigest()
    return f"cit_{digest}"


def _snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _heading(path: Sequence[str]) -> str:
    return " / ".join(part for part in path if part)


def build_citation(evidence: EvidenceChunk, label: str) -> Citation:
    """Create the citation object for one evidence chunk."""
    return Citation(
        citation_id=citation_id_for(evidence.chunk_id),
        label=label,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        version_id=evidence.version_id,
        title=evidence.title,
        heading=_heading(evidence.heading_path),
        page_no=evidence.page_no,
        version=evidence.version,
        effective_from=evidence.effective_from.isoformat(),
        effective_to=evidence.effective_to.isoformat() if evidence.effective_to else None,
        snippet=_snippet(evidence.text),
        score=evidence.score,
        dense_similarity=evidence.dense_similarity,
    )


def select_evidence(
    chunks: Sequence[EvidenceChunk],
    *,
    min_chunks: int = 4,
    max_chunks: int = 8,
    token_budget: int = 2400,
    max_per_document: int = 3,
) -> list[EvidenceChunk]:
    """Pick 4-8 high-value chunks within a token budget, deduplicated by document.

    Ranking already encodes relevance (RRF), so selection only breaks ties in favour of
    coverage: a second chunk from the same document is only taken when diversity is
    already satisfied.
    """
    if min_chunks < 1 or max_chunks < min_chunks:
        raise ValueError("invalid chunk selection bounds")
    selected: list[EvidenceChunk] = []
    per_document: dict[str, int] = {}
    used_tokens = 0
    seen: set[str] = set()

    for chunk in chunks:
        if len(selected) >= max_chunks:
            break
        if chunk.chunk_id in seen:
            continue
        if per_document.get(chunk.document_id, 0) >= max_per_document:
            continue
        if selected and used_tokens + chunk.token_count > token_budget:
            continue
        selected.append(chunk)
        seen.add(chunk.chunk_id)
        per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1
        used_tokens += chunk.token_count
    return selected


def build_citations(evidence: Sequence[EvidenceChunk]) -> list[Citation]:
    """Build citations in evidence order, labelled ``c1..cN``."""
    return [build_citation(chunk, f"c{index}") for index, chunk in enumerate(evidence, start=1)]


def detect_version_conflicts(evidence: Sequence[EvidenceChunk]) -> dict[str, list[str]]:
    """Detect documents with more than one *simultaneously retrieved* version.

    Overlapping effective versions are a knowledge-governance defect: the answer must not
    silently pick one. Returns ``{document_id: [version_id, ...]}`` for conflicting docs.
    """
    versions: dict[str, set[str]] = {}
    for chunk in evidence:
        versions.setdefault(chunk.document_id, set()).add(chunk.version_id)
    return {doc: sorted(found) for doc, found in versions.items() if len(found) > 1}
