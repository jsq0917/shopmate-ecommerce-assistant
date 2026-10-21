"""Regression tests for the ``NO_EVIDENCE`` / ``CONFLICT`` sentinel fail-open (stage 16).

Stage 13 found that a sentinel followed by citation labels (``NO_EVIDENCE [c1]``) bypassed
the exact-equality check, was accepted by the citation guard, and was then shown to the
user as the answer (``eval-058`` / ``eval-061``). These five cases pin the fixed
behaviour, including the one that must **not** change: a normal, label-bearing answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.citations import EvidenceChunk, build_citations
from shopmate_ecommerce_assistant.rag.policy_qa import (
    CONFLICT_TEXT,
    REFUSAL_TEXT,
    PolicyQAService,
    citation_issues,
    commitment_issues,
)
from shopmate_ecommerce_assistant.rag.retrieval import (
    RetrievalMode,
    RetrievalResult,
    RetrievalScope,
)

SCOPE = RetrievalScope(
    shop_id="11111111-1111-1111-1111-111111111111",
    at=datetime(2026, 10, 19, tzinfo=UTC),
)


def _retrieval() -> RetrievalResult:
    evidence = [
        EvidenceChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            version_id="ver-1",
            title="七天无理由退货政策（中国大陆）",
            heading_path=("七天无理由退货",),
            page_no=1,
            version="2026.10.1",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=None,
            text="消费者自签收之日起七日内，可申请无理由退货。",
            token_count=40,
            score=0.03,
            dense_similarity=0.71,
            rrf_rank=1,
        )
    ]
    return RetrievalResult(
        query="七天无理由怎么退",
        scope=SCOPE,
        mode=RetrievalMode.HYBRID,
        evidence=tuple(evidence),
        citations=tuple(build_citations(evidence)),
        evidence_sufficient=True,
        top_dense_similarity=0.71,
        conflicts={},
        audit={"embedding": {"model": "bge-m3", "fingerprint": "abc"}, "latency_ms": 1.0},
    )


class _Retriever:
    async def retrieve(self, query: str, scope: RetrievalScope, **_: Any) -> RetrievalResult:
        return _retrieval()


class _Model:
    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, *, system: str, user: str) -> str:
        return self.text


def _service(draft: str) -> PolicyQAService:
    return PolicyQAService(
        retriever=_Retriever(),  # type: ignore[arg-type]
        answer_model=_Model(draft),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
    )


async def test_bare_no_evidence_is_refused() -> None:
    answer = await _service("NO_EVIDENCE").answer("火星能配送吗", SCOPE)
    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT
    assert answer.citations == ()


async def test_no_evidence_with_citation_label_is_refused() -> None:
    """The stage-13 fail-open: ``NO_EVIDENCE [c1]`` used to be returned verbatim."""
    answer = await _service("NO_EVIDENCE [c1]").answer("火星能配送吗", SCOPE)
    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT
    assert answer.citations == ()
    assert "NO_EVIDENCE" not in answer.answer_text


async def test_lowercase_conflict_with_punctuation_hands_off() -> None:
    answer = await _service("conflict。").answer("两个版本冲突吗", SCOPE)
    assert answer.status == "handoff"
    assert answer.answer_text == CONFLICT_TEXT


async def test_no_evidence_with_label_and_trailing_period_is_refused() -> None:
    answer = await _service("NO_EVIDENCE[c1].").answer("火星能配送吗", SCOPE)
    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT


async def test_a_normal_cited_answer_is_not_mistaken_for_a_sentinel() -> None:
    draft = "消费者自签收之日起七日内可申请无理由退货[c1]。"
    answer = await _service(draft).answer("七天无理由怎么退", SCOPE)
    assert answer.status == "answered"
    assert answer.answer_text == draft
    assert [citation.label for citation in answer.citations] == ["c1"]


@pytest.mark.parametrize(
    "text",
    ["NO_EVIDENCE [c1]", "CONFLICT [c1][c2]", "  no_evidence  ", "NO_EVIDENCE[c1]."],
)
def test_citation_guard_skips_sentinels_instead_of_demanding_labels(text: str) -> None:
    assert citation_issues(text, list(build_citations(_retrieval().evidence))) == []


def test_a_commitment_is_still_caught_after_the_sentinel_change() -> None:
    """Guard against over-normalisation: money commitments must still be flagged."""
    assert commitment_issues("已为您退款，请查收。[c1]") != []
