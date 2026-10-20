"""Citation stability, evidence selection and version-conflict detection."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from shopmate_ecommerce_assistant.rag.citations import (
    EvidenceChunk,
    build_citations,
    citation_id_for,
    detect_version_conflicts,
    select_evidence,
)


def _chunk(
    chunk_id: str,
    *,
    document_id: str = "doc-1",
    version_id: str = "ver-1",
    version: str = "2026.10.1",
    rank: int = 1,
    tokens: int = 100,
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        title="七天无理由退货政策（中国大陆）",
        heading_path=("七天无理由退货政策（中国大陆）", "七天无理由退货条件"),
        page_no=1,
        version=version,
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=None,
        text="消费者自签收之日起七日内，可对符合条件的商品申请无理由退货。",
        token_count=tokens,
        score=0.032,
        dense_similarity=0.61,
        rrf_rank=rank,
    )


def test_citation_id_is_stable_and_chunk_specific() -> None:
    assert citation_id_for("chunk-a") == citation_id_for("chunk-a")
    assert citation_id_for("chunk-a") != citation_id_for("chunk-b")


def test_citation_carries_every_audit_field() -> None:
    citation = build_citations([_chunk("chunk-a")])[0]
    assert citation.label == "c1"
    assert citation.document_id == "doc-1"
    assert citation.chunk_id == "chunk-a"
    assert citation.version == "2026.10.1"
    assert citation.heading == "七天无理由退货政策（中国大陆） / 七天无理由退货条件"
    assert citation.page_no == 1
    assert citation.effective_from.startswith("2026-10-01")
    assert citation.effective_to is None
    assert "签收之日起七日内" in citation.snippet
    payload = citation.as_dict()
    assert payload["citation_id"] == citation.citation_id
    assert payload["dense_similarity"] == 0.61


def test_snippet_is_truncated_without_losing_the_start() -> None:
    long_text = "退货" * 400
    long_chunk = replace(_chunk("chunk-long"), text=long_text)
    snippet = build_citations([long_chunk])[0].snippet
    assert len(snippet) <= 220
    assert snippet.endswith("…")


def test_selection_respects_bounds_and_token_budget() -> None:
    chunks = [_chunk(f"c{index}", document_id=f"doc-{index}", rank=index) for index in range(1, 11)]
    selected = select_evidence(chunks, min_chunks=4, max_chunks=6, token_budget=1000)
    assert 4 <= len(selected) <= 6
    assert sum(chunk.token_count for chunk in selected) <= 1000


def test_selection_limits_chunks_per_document() -> None:
    chunks = [_chunk(f"c{index}", document_id="doc-1", rank=index) for index in range(1, 8)]
    selected = select_evidence(chunks, min_chunks=4, max_chunks=8, max_per_document=2)
    assert len(selected) == 2


def test_selection_deduplicates_chunk_ids() -> None:
    chunks = [_chunk("same", document_id=f"doc-{index}") for index in range(3)]
    selected = select_evidence(chunks, min_chunks=1, max_chunks=8)
    assert [chunk.chunk_id for chunk in selected] == ["same"]


def test_version_conflict_is_detected() -> None:
    chunks = [
        _chunk("a", document_id="doc-1", version_id="ver-old", version="2026.07.1"),
        _chunk("b", document_id="doc-1", version_id="ver-new", version="2026.10.1"),
        _chunk("c", document_id="doc-2", version_id="ver-x"),
    ]
    conflicts = detect_version_conflicts(chunks)
    assert list(conflicts) == ["doc-1"]
    assert sorted(conflicts["doc-1"]) == ["ver-new", "ver-old"]


def test_single_version_has_no_conflict() -> None:
    assert detect_version_conflicts([_chunk("a"), _chunk("b")]) == {}
