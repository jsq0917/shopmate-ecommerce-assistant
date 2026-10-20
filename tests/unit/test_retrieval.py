"""Hybrid retrieval behaviour: fusion, branch failures, scoping and evidence gating."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.repositories.knowledge import ChunkMetadata
from shopmate_ecommerce_assistant.rag.errors import InvalidEmbeddingError, RetrievalError
from shopmate_ecommerce_assistant.rag.milvus_store import HybridSearchResult, SearchHit
from shopmate_ecommerce_assistant.rag.retrieval import (
    DocumentRetriever,
    RetrievalMode,
    RetrievalScope,
)
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

SHOP = UUID("11111111-1111-1111-1111-111111111111")
OTHER_SHOP = UUID("22222222-2222-2222-2222-222222222222")
KB = UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 10, 19, tzinfo=UTC)


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "retrieval_min_chunks": 4,
        "retrieval_max_chunks": 8,
        "retrieval_context_token_budget": 5000,
        "policy_min_evidence_similarity": 0.42,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


def _hit(chunk_id: str, score: float, *, version_id: str = "v1") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        text=f"片段 {chunk_id}",
        document_id="doc-1",
        version_id=version_id,
        knowledge_base_id=str(KB),
        doc_type="policy",
        page_no=1,
        heading_path=("退货政策", "条件"),
        embedding_model="fake-hybrid",
        metadata={"region": "CN", "locale": "zh-CN"},
    )


def _synthetic_uuid(value: str) -> UUID:
    """Derive a deterministic UUID from a short label like ``doc-1``."""
    if "-" in value:
        try:
            return UUID(int=int(value.split("-")[-1], 16))
        except ValueError:
            return uuid4()
    return uuid4()


def _meta(
    chunk_id: str,
    *,
    shop_id: UUID = SHOP,
    document_id: str = "doc-1",
    version_id: str = "v1",
    version: str = "2026.10.1",
    effective_to: datetime | None = None,
    is_enabled: bool = True,
    parse_status: str = "ready",
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=UUID(chunk_id),
        shop_id=shop_id,
        knowledge_base_id=KB,
        document_id=_synthetic_uuid(document_id),
        version_id=_synthetic_uuid(version_id),
        parent_id=None,
        chunk_index=1,
        heading_path=("退货政策", "条件"),
        page_no=1,
        text="消费者自签收之日起七日内可申请无理由退货。",
        token_count=80,
        is_enabled=is_enabled,
        deleted_at=None,
        title="七天无理由退货政策（中国大陆）",
        doc_type="policy",
        locale="zh-CN",
        region="CN",
        document_status="active",
        document_deleted_at=None,
        version=version,
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=effective_to,
        parse_status=parse_status,
        metadata_jsonb={},
    )


class FakeStore:
    """Minimal store double that records which branches were exercised."""

    def __init__(
        self,
        *,
        hits: Sequence[SearchHit] | None = None,
        similarities: dict[str, float] | None = None,
        hybrid_error: Exception | None = None,
        dense_error: Exception | None = None,
        sparse_error: Exception | None = None,
        dense_hits: Sequence[SearchHit] | None = None,
    ) -> None:
        self.collection = "fake"
        self.hits = list(hits or [])
        self.dense_hits = list(dense_hits or [])
        self.similarities = similarities or {}
        self.hybrid_error = hybrid_error
        self.dense_error = dense_error
        self.sparse_error = sparse_error
        self.calls: list[str] = []

    def build_filter(self, **kwargs: Any) -> str:
        self.calls.append("build_filter")
        return "filter"

    def hybrid_search(self, dense: Any, sparse: Any, **kwargs: Any) -> HybridSearchResult:
        self.calls.append("hybrid_search")
        if self.hybrid_error is not None:
            raise self.hybrid_error
        return HybridSearchResult(
            hits=tuple(self.hits),
            dense_limit=kwargs["dense_limit"],
            sparse_limit=kwargs["sparse_limit"],
            rrf_k=kwargs["rrf_k"],
        )

    def dense_search(self, dense: Any, **kwargs: Any) -> list[SearchHit]:
        self.calls.append("dense_search")
        if self.dense_error is not None:
            raise self.dense_error
        return self.dense_hits or self.hits

    def sparse_search(self, sparse: Any, **kwargs: Any) -> list[SearchHit]:
        self.calls.append("sparse_search")
        if self.sparse_error is not None:
            raise self.sparse_error
        return self.hits

    def dense_similarity(self, dense: Any, chunk_ids: Sequence[str]) -> dict[str, float]:
        self.calls.append("dense_similarity")
        return {chunk_id: self.similarities.get(chunk_id, 0.0) for chunk_id in chunk_ids}


def _retriever(
    store: FakeStore,
    metas: dict[str, ChunkMetadata],
    *,
    settings: Settings | None = None,
    provider: Any | None = None,
) -> DocumentRetriever:
    async def authorizer(chunk_ids: Sequence[UUID]) -> dict[UUID, ChunkMetadata]:
        return {chunk_id: metas[str(chunk_id)] for chunk_id in chunk_ids if str(chunk_id) in metas}

    return DocumentRetriever(
        settings=settings or _settings(),
        provider=provider or FakeHybridEmbeddingProvider(),
        store=store,  # type: ignore[arg-type]
        authorizer=authorizer,
        clock=lambda: NOW,
    )


def _scope(**overrides: Any) -> RetrievalScope:
    payload: dict[str, Any] = {
        "shop_id": str(SHOP),
        "knowledge_base_id": str(KB),
        "locale": "zh-CN",
        "region": "CN",
        "at": NOW,
    }
    payload.update(overrides)
    return RetrievalScope(**payload)


def _chunk_ids(count: int) -> list[str]:
    return [str(uuid4()) for _ in range(count)]


def _metas(ids: Sequence[str], **overrides: Any) -> dict[str, ChunkMetadata]:
    """One document per chunk, so selection is not capped by the per-document limit."""
    return {
        chunk_id: _meta(chunk_id, document_id=f"doc-{index + 1}", **overrides)
        for index, chunk_id in enumerate(ids)
    }


@pytest.mark.asyncio
async def test_hybrid_retrieval_returns_citations_and_audit() -> None:
    ids = _chunk_ids(5)
    hits = [_hit(chunk_id, 0.033 - index * 0.001) for index, chunk_id in enumerate(ids)]
    store = FakeStore(hits=hits, similarities={chunk_id: 0.7 for chunk_id in ids})
    retriever = _retriever(store, _metas(ids))

    result = await retriever.retrieve("七天无理由退货从什么时候开始计算？", _scope())

    assert "hybrid_search" in store.calls, "生产检索必须走 hybrid_search"
    assert result.mode is RetrievalMode.HYBRID
    assert len(result.evidence) >= 4
    assert len(result.citations) == len(result.evidence)
    assert [citation.label for citation in result.citations][:2] == ["c1", "c2"]
    assert result.evidence_sufficient is True
    assert result.audit["branch"] == {"dense": "ok", "sparse": "ok"}
    assert result.audit["rrf_k"] == 60
    assert result.audit["dense_limit"] == 30
    assert result.audit["sparse_limit"] == 30
    assert result.audit["embedding"]["fingerprint"] == "test-fingerprint"
    assert result.audit["selected_chunk_ids"] == [chunk.chunk_id for chunk in result.evidence]


@pytest.mark.asyncio
async def test_sparse_branch_failure_raises_instead_of_degrading() -> None:
    ids = _chunk_ids(2)
    store = FakeStore(
        hits=[_hit(chunk_id, 0.03) for chunk_id in ids],
        hybrid_error=RetrievalError("HYBRID_SEARCH_FAILED", "混合检索失败"),
        sparse_error=RetrievalError("SPARSE_BRANCH_FAILED", "sparse 检索失败"),
    )
    retriever = _retriever(store, _metas(ids))

    with pytest.raises(RetrievalError) as excinfo:
        await retriever.retrieve("退货期限", _scope())

    assert excinfo.value.code == "SPARSE_BRANCH_FAILED"
    assert "dense_search" in store.calls


@pytest.mark.asyncio
async def test_dense_branch_failure_raises_instead_of_degrading() -> None:
    ids = _chunk_ids(2)
    store = FakeStore(
        hits=[_hit(chunk_id, 0.03) for chunk_id in ids],
        hybrid_error=RetrievalError("HYBRID_SEARCH_FAILED", "混合检索失败"),
        dense_error=RetrievalError("DENSE_BRANCH_FAILED", "dense 检索失败"),
    )
    retriever = _retriever(store, _metas(ids))

    with pytest.raises(RetrievalError) as excinfo:
        await retriever.retrieve("退货期限", _scope())

    assert excinfo.value.code == "DENSE_BRANCH_FAILED"


@pytest.mark.asyncio
async def test_expired_and_cross_shop_chunks_are_rejected() -> None:
    valid, expired, foreign = _chunk_ids(3)
    hits = [_hit(valid, 0.033), _hit(expired, 0.032), _hit(foreign, 0.031)]
    store = FakeStore(hits=hits, similarities={valid: 0.7, expired: 0.7, foreign: 0.7})
    metas = {
        valid: _meta(valid),
        expired: _meta(expired, effective_to=datetime(2026, 10, 1, tzinfo=UTC)),
        foreign: _meta(foreign, shop_id=OTHER_SHOP),
    }
    retriever = _retriever(store, metas)

    result = await retriever.retrieve("退货期限", _scope())

    assert [chunk.chunk_id for chunk in result.evidence] == [valid]
    assert result.audit["rejected"]["expired"] == 1
    assert result.audit["rejected"]["cross_shop"] == 1


@pytest.mark.asyncio
async def test_all_candidates_rejected_yields_no_evidence() -> None:
    ids = _chunk_ids(2)
    store = FakeStore(hits=[_hit(chunk_id, 0.03) for chunk_id in ids])
    retriever = _retriever(store, _metas(ids, parse_status="failed", is_enabled=False))

    result = await retriever.retrieve("退货期限", _scope())

    assert result.evidence == ()
    assert result.citations == ()
    assert result.evidence_sufficient is False
    assert result.audit["rejected"]["version_not_ready"] == 2
    assert result.audit["rejected"]["chunk_disabled"] == 2


@pytest.mark.asyncio
async def test_low_similarity_blocks_the_answer_gate() -> None:
    ids = _chunk_ids(4)
    store = FakeStore(
        hits=[_hit(chunk_id, 0.03) for chunk_id in ids],
        similarities={chunk_id: 0.11 for chunk_id in ids},
    )
    retriever = _retriever(store, _metas(ids))

    result = await retriever.retrieve("门店停车场在哪里", _scope())

    assert result.evidence, "候选仍应可追溯"
    assert result.evidence_sufficient is False


@pytest.mark.asyncio
async def test_overlapping_versions_are_flagged_as_conflict() -> None:
    first, second = _chunk_ids(2)
    hits = [_hit(first, 0.033, version_id="v1"), _hit(second, 0.032, version_id="v2")]
    store = FakeStore(hits=hits, similarities={first: 0.7, second: 0.7})
    metas = {
        first: _meta(first, version_id="v1", version="2026.09.1"),
        second: _meta(second, version_id="v2", version="2026.10.1"),
    }
    retriever = _retriever(store, metas)

    result = await retriever.retrieve("逾期退货手续费", _scope())

    assert result.conflicts, "同一文档的两个有效版本必须被标记为冲突"


@pytest.mark.asyncio
async def test_dense_only_mode_is_an_explicit_ablation() -> None:
    ids = _chunk_ids(4)
    store = FakeStore(
        hits=[_hit(chunk_id, 0.62 - index * 0.01) for index, chunk_id in enumerate(ids)],
        similarities={chunk_id: 0.7 for chunk_id in ids},
    )
    retriever = _retriever(store, _metas(ids))

    result = await retriever.retrieve("退货期限", _scope(), mode=RetrievalMode.DENSE_ONLY_ABLATION)

    assert "hybrid_search" not in store.calls
    assert result.mode is RetrievalMode.DENSE_ONLY_ABLATION
    assert result.audit["branch"]["sparse"] == "disabled_by_request"


@pytest.mark.asyncio
async def test_query_embedding_failure_is_reported_with_a_code() -> None:
    class BrokenProvider(FakeHybridEmbeddingProvider):
        def embed_query_hybrid(self, text: str) -> Any:
            raise InvalidEmbeddingError("EMBEDDING_NON_FINITE", "查询向量含 NaN")

    ids = _chunk_ids(1)
    store = FakeStore(hits=[_hit(ids[0], 0.03)])
    retriever = _retriever(store, _metas(ids), provider=BrokenProvider())

    with pytest.raises(RetrievalError) as excinfo:
        await retriever.retrieve("退货期限", _scope())

    assert excinfo.value.code == "QUERY_EMBEDDING_FAILED"


@pytest.mark.asyncio
async def test_invalid_shop_id_is_rejected_before_querying() -> None:
    store = FakeStore(hits=[])
    retriever = _retriever(store, {})

    with pytest.raises(RetrievalError) as excinfo:
        await retriever.retrieve("退货期限", _scope(shop_id="demo-shop"))

    assert excinfo.value.code == "INVALID_SCOPE"


@pytest.mark.asyncio
async def test_empty_query_is_rejected() -> None:
    retriever = _retriever(FakeStore(), {})
    with pytest.raises(RetrievalError) as excinfo:
        await retriever.retrieve("   ", _scope())
    assert excinfo.value.code == "EMPTY_QUERY"
