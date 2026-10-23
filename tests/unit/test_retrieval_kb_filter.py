"""Retrieval scoping for a multi-knowledge-base selection (stage 18).

Two enforcement layers must agree:

* the Milvus expression pushes the selection down (``knowledge_base_id in [...]``);
* the PostgreSQL re-check rejects any fused candidate outside the selection, because a
  vector index is not an authority on permissions.

``docs/06-api.md`` §6.1 documents the selection semantics; these tests pin the mechanics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

# `rag.retrieval` -> `db.repositories.knowledge` -> ... -> `safety.output_guard` ->
# `rag.policy_qa` is a known import cycle; loading `safety` first keeps collection clean
# (same workaround as tests/unit/test_llm_profile.py, see docs/project-status.md §23.5).
from shopmate_ecommerce_assistant import safety as _safety  # noqa: F401
from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.db.repositories.knowledge import (
    ChunkMetadata,
    authorization_issues,
)
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore
from shopmate_ecommerce_assistant.rag.retrieval import RetrievalScope


def _store() -> MilvusKnowledgeStore:
    """A store instance used only for ``build_filter`` (no Milvus connection needed)."""
    return MilvusKnowledgeStore(get_settings())


def test_filter_uses_in_clause_for_multiple_knowledge_bases() -> None:
    kb_a, kb_b = str(uuid4()), str(uuid4())
    expr = _store().build_filter(
        shop_id="shop-1", knowledge_base_ids=(kb_a, kb_b), locale=None, region=None
    )
    assert f'knowledge_base_id in ["{kb_a}", "{kb_b}"]' in expr


def test_filter_falls_back_to_equality_for_a_single_knowledge_base() -> None:
    kb = str(uuid4())
    expr = _store().build_filter(shop_id="shop-1", knowledge_base_id=kb)
    assert f'knowledge_base_id == "{kb}"' in expr
    assert " in [" not in expr


def test_filter_without_selection_has_no_knowledge_base_clause() -> None:
    expr = _store().build_filter(shop_id="shop-1")
    assert "knowledge_base_id" not in expr


def test_scope_records_the_selection_in_the_audit_snapshot() -> None:
    kb = str(uuid4())
    scope = RetrievalScope(shop_id="shop-1", knowledge_base_ids=(kb,), locale=None, region=None)
    assert scope.as_dict()["knowledge_base_ids"] == [kb]


def _metadata(kb_id, *, shop_id=None) -> ChunkMetadata:
    now = datetime.now(UTC)
    return ChunkMetadata(
        chunk_id=uuid4(),
        shop_id=shop_id or uuid4(),
        knowledge_base_id=kb_id,
        document_id=uuid4(),
        version_id=uuid4(),
        parent_id=None,
        chunk_index=0,
        heading_path=("七天无理由",),
        page_no=1,
        text="合成片段",
        token_count=8,
        is_enabled=True,
        deleted_at=None,
        title="退货政策",
        doc_type="policy",
        locale="zh-CN",
        region="CN",
        document_status="active",
        document_deleted_at=None,
        version="2026.10.1",
        effective_from=now.replace(year=now.year - 1),
        effective_to=None,
        parse_status="ready",
        metadata_jsonb={},
    )


def test_authorizer_rejects_a_chunk_outside_the_selection() -> None:
    selected, other, shop_id = uuid4(), uuid4(), uuid4()
    meta = _metadata(other, shop_id=shop_id)
    issues = authorization_issues(
        meta,
        shop_id=shop_id,
        knowledge_base_id=None,
        knowledge_base_ids={selected},
        locale=None,
        region=None,
        at=datetime.now(UTC),
    )
    assert issues == ["wrong_knowledge_base"]


def test_authorizer_accepts_a_chunk_inside_the_selection() -> None:
    selected, shop_id = uuid4(), uuid4()
    meta = _metadata(selected, shop_id=shop_id)
    issues = authorization_issues(
        meta,
        shop_id=shop_id,
        knowledge_base_id=None,
        knowledge_base_ids={selected, uuid4()},
        locale=None,
        region=None,
        at=datetime.now(UTC),
    )
    assert issues == []


class _FakeProvider:
    """Minimal embedding provider: one canned query vector, no model weights."""

    class _Vector:
        dense = (0.1, 0.2)
        sparse = {1: 0.5}

    class _Meta:
        model = "fake"
        dimension = 2
        revision = "test"

        def as_dict(self) -> dict[str, object]:
            return {"model": self.model, "dimension": self.dimension, "revision": self.revision}

    metadata = _Meta()

    def embed_query_hybrid(self, query: str):  # noqa: ANN001 - test double
        return self._Vector()


class _RecordingStore:
    """Records what `build_filter` receives and returns no candidates."""

    def __init__(self) -> None:
        self.filter_kwargs: dict[str, object] = {}

    def build_filter(self, **kwargs: object) -> str:
        self.filter_kwargs = kwargs
        return 'shop_id == "x"'

    def hybrid_search(self, *args: object, **kwargs: object):
        from shopmate_ecommerce_assistant.rag.milvus_store import HybridSearchResult

        return HybridSearchResult(hits=(), dense_limit=30, sparse_limit=30, rrf_k=60)

    def dense_search(self, *args: object, **kwargs: object) -> list:
        return []


async def test_retrieve_pushes_the_selection_into_the_store_filter() -> None:
    """Regression: ``retrieve`` rebuilds the scope for the request moment.

    That rebuild used to drop ``knowledge_base_ids``, so the selection was silently
    ignored and every knowledge base of the shop was searched.
    """
    from shopmate_ecommerce_assistant.rag.retrieval import DocumentRetriever

    async def _authorizer(chunk_ids):  # noqa: ANN001 - test double
        return {}

    store = _RecordingStore()
    retriever = DocumentRetriever(
        settings=get_settings(), store=store, provider=_FakeProvider(), authorizer=_authorizer
    )
    kb_a, kb_b = str(uuid4()), str(uuid4())
    await retriever.retrieve(
        "退货期限是多久？",
        RetrievalScope(
            shop_id=str(uuid4()), knowledge_base_ids=(kb_a, kb_b), locale=None, region=None
        ),
    )
    assert store.filter_kwargs["knowledge_base_ids"] == (kb_a, kb_b), (
        "retrieve() must keep the knowledge-base selection in the pushdown filter"
    )
