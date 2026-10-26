"""FAQ-cache gates on the policy answer path: replay fidelity and risk gating.

Three behaviours are pinned here:

1. A cache hit must replay citations *completely* — the stored payload keys the
   preview ``snippet`` (``Citation.as_dict``), so the replay used to read
   ``excerpt`` and every cached citation lost its preview text (AGENTS.md §10.5:
   引用必须可预览).
2. Only a low-risk turn may read or write the cache (stage-8 cacheability). A
   caller that cannot speak for the turn's risk — the eval harness and scripts
   pass no ``risk_level`` — gets the uncached path, fail-closed like
   ``FaqService.remember``.
3. A multi-KB scope keys the cache by the sorted, comma-joined ids, so two
   different selections never share an entry even when they cite the same versions.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import UTC, datetime
from typing import Any

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.citations import EvidenceChunk, build_citations
from shopmate_ecommerce_assistant.rag.faq import FaqAnswerCache
from shopmate_ecommerce_assistant.rag.policy_qa import PolicyQAService
from shopmate_ecommerce_assistant.rag.retrieval import (
    RetrievalMode,
    RetrievalResult,
    RetrievalScope,
)

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
SHOP = "11111111-1111-1111-1111-111111111111"
SCOPE = RetrievalScope(
    shop_id=SHOP,
    at=datetime(2026, 10, 19, tzinfo=UTC),
)
DRAFT = "消费者自签收之日起七日内可申请无理由退货[c1]。"
QUESTION = "七天无理由怎么退"


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
        query=QUESTION,
        scope=SCOPE,
        mode=RetrievalMode.HYBRID,
        evidence=tuple(evidence),
        citations=tuple(build_citations(evidence)),
        evidence_sufficient=True,
        top_dense_similarity=0.71,
        conflicts={},
        audit={},
    )


class _Retriever:
    async def retrieve(self, query: str, scope: RetrievalScope, **_: Any) -> RetrievalResult:
        return _retrieval()


class _CountingModel:
    name = "stub"

    def __init__(self, text: str, calls: list[int]) -> None:
        self._text = text
        self._calls = calls

    def complete(self, *, system: str, user: str, generation=None) -> str:
        self._calls.append(1)
        return self._text


class MemoryBackend:
    """Dict-backed Redis double (same contract as ``tests/unit/test_faq_cache.py``)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def keys(self, pattern: str) -> list[str]:
        return [key for key in list(self.data) if fnmatch.fnmatch(key, pattern)]


def _service(calls: list[int], backend: MemoryBackend) -> PolicyQAService:
    return PolicyQAService(
        retriever=_Retriever(),  # type: ignore[arg-type]
        answer_model=_CountingModel(DRAFT, calls),
        settings=SETTINGS,
        faq_cache=FaqAnswerCache(backend, settings=SETTINGS),
    )


async def test_cache_hit_replays_the_citation_snippet() -> None:
    backend = MemoryBackend()
    calls: list[int] = []
    service = _service(calls, backend)

    first = await service.answer(QUESTION, SCOPE, risk_level="low")
    assert first.audit["decision"] == "answered"
    assert len(backend.data) == 1

    # The stored payload must carry the preview under the "snippet" key, and the
    # replay must read that key: "excerpt" used to yield an empty preview.
    stored = json.loads(next(iter(backend.data.values())))
    assert stored["citations"][0]["snippet"]

    second = await service.answer(QUESTION, SCOPE, risk_level="low")
    assert second.audit["decision"] == "answered_cached"
    assert len(calls) == 1, "the second turn must be served from the cache, not the model"
    assert second.citations[0].snippet, "cached citations must keep a non-empty preview"
    assert second.citations[0].snippet == first.citations[0].snippet
    # The replay must construct a *complete* Citation: missing required fields
    # (score/dense_similarity) used to raise TypeError and kill the whole turn.
    assert second.citations[0].score == first.citations[0].score
    assert second.citations[0].dense_similarity == first.citations[0].dense_similarity


async def test_medium_risk_turn_neither_reads_nor_writes_the_cache() -> None:
    backend = MemoryBackend()
    calls: list[int] = []
    service = _service(calls, backend)

    answer = await service.answer(QUESTION, SCOPE, risk_level="medium")
    assert answer.status == "answered"
    assert answer.audit["faq_cache"] == {"hit": False, "reason": "risk_not_cacheable"}
    assert not backend.data, "a medium-risk turn must not be cached"
    assert len(calls) == 1


async def test_missing_risk_level_is_fail_closed_like_medium_risk() -> None:
    """Eval harness / scripts call ``answer()`` without a risk level — no caching."""
    backend = MemoryBackend()
    calls: list[int] = []
    service = _service(calls, backend)

    answer = await service.answer(QUESTION, SCOPE)
    assert answer.audit["faq_cache"] == {"hit": False, "reason": "risk_not_cacheable"}
    assert not backend.data


async def test_medium_risk_does_not_serve_a_pre_populated_cache() -> None:
    backend = MemoryBackend()
    calls: list[int] = []
    service = _service(calls, backend)

    await service.answer(QUESTION, SCOPE, risk_level="low")
    assert len(backend.data) == 1
    calls.clear()

    answer = await service.answer(QUESTION, SCOPE, risk_level="medium")
    assert answer.audit["faq_cache"]["reason"] == "risk_not_cacheable"
    assert len(calls) == 1, "an escalated turn must still get a fresh model answer"


def test_cache_kb_id_is_order_insensitive_and_selection_sensitive() -> None:
    ab = RetrievalScope(shop_id=SHOP, knowledge_base_ids=("kb-b", "kb-a"))
    ba = RetrievalScope(shop_id=SHOP, knowledge_base_ids=("kb-a", "kb-b"))
    ac = RetrievalScope(shop_id=SHOP, knowledge_base_ids=("kb-a", "kb-c"))
    single = RetrievalScope(shop_id=SHOP, knowledge_base_id="kb-a")

    assert PolicyQAService._cache_kb_id(ab) == PolicyQAService._cache_kb_id(ba) == "kb-a,kb-b"
    assert PolicyQAService._cache_kb_id(ab) != PolicyQAService._cache_kb_id(ac)
    assert PolicyQAService._cache_kb_id(single) == "kb-a"
