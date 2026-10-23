"""Policy QA rules: evidence gating, untrusted evidence, citation enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.citations import Citation, EvidenceChunk, build_citations
from shopmate_ecommerce_assistant.rag.policy_qa import (
    CONFLICT_TEXT,
    REFUSAL_TEXT,
    SYSTEM_PROMPT,
    UNCITED_TEXT,
    AnswerModelError,
    PolicyQAService,
    build_policy_prompt,
    citation_issues,
    used_labels,
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


def _evidence(
    chunk_id: str, *, document_id: str = "doc-1", version_id: str = "ver-1"
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        title="七天无理由退货政策（中国大陆）",
        heading_path=("七天无理由退货政策（中国大陆）", "七天无理由退货条件"),
        page_no=1,
        version="2026.10.1",
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=None,
        text="消费者自签收之日起七日内，可对符合条件的商品申请无理由退货。",
        token_count=60,
        score=0.033,
        dense_similarity=0.68,
        rrf_rank=1,
    )


def _result(
    *,
    sufficient: bool = True,
    conflicts: dict[str, list[str]] | None = None,
    chunks: list[EvidenceChunk] | None = None,
) -> RetrievalResult:
    evidence = chunks if chunks is not None else [_evidence("chunk-1")]
    citations = build_citations(evidence)
    return RetrievalResult(
        query="七天无理由退货怎么算时间",
        scope=SCOPE,
        mode=RetrievalMode.HYBRID,
        evidence=tuple(evidence),
        citations=tuple(citations),
        evidence_sufficient=sufficient,
        top_dense_similarity=0.68 if sufficient else 0.1,
        conflicts=conflicts or {},
        audit={
            "embedding": {"model": "bge-m3", "fingerprint": "abc"},
            "latency_ms": 1.0,
        },
    )


class StubRetriever:
    def __init__(self, result: RetrievalResult, *, calls: list[str] | None = None) -> None:
        self._result = result
        self.calls = calls if calls is not None else []

    async def retrieve(self, query: str, scope: RetrievalScope, **_: Any) -> RetrievalResult:
        self.calls.append(query)
        return self._result


class StubModel:
    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []
        self.generations: list[object] = []

    def complete(self, *, system: str, user: str, generation=None) -> str:
        self.prompts.append(user)
        self.generations.append(generation)
        return self.text


def _service(result: RetrievalResult, model: Any | None) -> PolicyQAService:
    return PolicyQAService(
        retriever=StubRetriever(result),  # type: ignore[arg-type]
        answer_model=model,
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
    )


# -- prompt ----------------------------------------------------------------


def test_prompt_marks_evidence_as_untrusted() -> None:
    citations = build_citations([_evidence("chunk-1")])
    prompt = build_policy_prompt("七天无理由退货怎么算？", citations)
    assert '<evidence untrusted="true">' in prompt
    assert "[c1]" in prompt
    assert "七天无理由退货怎么算？" in prompt


def test_system_prompt_forbids_following_document_instructions() -> None:
    assert "不可信" in SYSTEM_PROMPT
    assert "不得执行" in SYSTEM_PROMPT
    assert "NO_EVIDENCE" in SYSTEM_PROMPT
    assert "CONFLICT" in SYSTEM_PROMPT


# -- citation guard --------------------------------------------------------


def test_used_labels_preserves_order_and_deduplicates() -> None:
    assert used_labels("结论一[c2]，结论二[c1]，再引用[c2]") == ["c2", "c1"]


def test_missing_citation_is_flagged() -> None:
    citations = build_citations([_evidence("chunk-1")])
    issues = citation_issues("退货期限为七天。", citations)
    assert "missing_citation" in issues


def test_unknown_citation_is_flagged() -> None:
    citations = build_citations([_evidence("chunk-1")])
    issues = citation_issues("退货期限为七天[c9]。", citations)
    assert any(issue.startswith("unknown_citation") for issue in issues)


def test_uncited_policy_sentence_is_flagged() -> None:
    citations = build_citations([_evidence("chunk-1")])
    issues = citation_issues("退货期限为七天[c1]。退货运费由消费者承担。", citations)
    assert "uncited_claim" in issues


def test_fully_cited_answer_passes() -> None:
    citations = build_citations([_evidence("chunk-1")])
    issues = citation_issues("自签收之日起七日内可申请无理由退货[c1]。", citations)
    assert issues == []


# -- service behaviour -----------------------------------------------------


@pytest.mark.asyncio
async def test_cited_answer_is_returned_with_only_used_citations() -> None:
    result = _result(chunks=[_evidence("chunk-1"), _evidence("chunk-2")])
    model = StubModel("自签收之日起七日内可申请无理由退货[c1]。")
    answer = await _service(result, model).answer("七天无理由怎么算", SCOPE)

    assert answer.status == "answered"
    assert answer.used_labels == ("c1",)
    assert [citation.label for citation in answer.citations] == ["c1"]
    assert "untrusted" in model.prompts[0]


@pytest.mark.asyncio
async def test_uncited_answer_hands_off_without_leaking_the_draft() -> None:
    result = _result()
    model = StubModel("退货期限是七天，运费由消费者承担。")
    answer = await _service(result, model).answer("七天无理由怎么算", SCOPE)

    assert answer.status == "handoff"
    assert answer.answer_text == UNCITED_TEXT
    assert "uncited_claim" in answer.reasons or "missing_citation" in answer.reasons
    assert "运费由消费者承担" not in answer.answer_text


@pytest.mark.asyncio
async def test_model_no_evidence_marker_becomes_refusal() -> None:
    answer = await _service(_result(), StubModel("NO_EVIDENCE")).answer("门店在哪", SCOPE)
    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT


@pytest.mark.asyncio
async def test_low_evidence_refuses_without_calling_the_model() -> None:
    model = StubModel("不应被调用[c1]。")
    answer = await _service(_result(sufficient=False), model).answer("门店在哪", SCOPE)

    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT
    assert model.prompts == []


@pytest.mark.asyncio
async def test_conflicting_versions_hand_off_without_calling_the_model() -> None:
    model = StubModel("不应被调用[c1]。")
    answer = await _service(_result(conflicts={"doc-1": ["ver-1", "ver-2"]}), model).answer(
        "逾期退货手续费多少", SCOPE
    )

    assert answer.status == "handoff"
    assert answer.answer_text == CONFLICT_TEXT
    assert model.prompts == []


@pytest.mark.asyncio
async def test_missing_answer_model_is_an_explicit_error() -> None:
    with pytest.raises(AnswerModelError) as excinfo:
        await _service(_result(), None).answer("七天无理由怎么算", SCOPE)
    assert excinfo.value.code == "ANSWER_MODEL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_audit_records_the_decision_and_model_fingerprint() -> None:
    model = StubModel("自签收之日起七日内可申请无理由退货[c1]。")
    answer = await _service(_result(), model).answer("七天无理由怎么算", SCOPE)
    assert answer.audit["decision"] == "answered"
    assert answer.audit["embedding"]["fingerprint"] == "abc"
    assert answer.audit["answer_digest"]


def test_citation_payload_is_json_ready() -> None:
    citation: Citation = build_citations([_evidence("chunk-1")])[0]
    payload = citation.as_dict()
    assert payload["page_no"] == 1
    assert payload["effective_from"].startswith("2026-10-01")
    assert payload["citation_id"].startswith("cit_")
