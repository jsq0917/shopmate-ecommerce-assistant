"""Query rewriting: short-query bypass, references, entities, bounds, embedding reuse."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.repositories.knowledge import ChunkMetadata
from shopmate_ecommerce_assistant.rag import query_rewrite
from shopmate_ecommerce_assistant.rag.milvus_store import HybridSearchResult, SearchHit
from shopmate_ecommerce_assistant.rag.policy_qa import PolicyQAService
from shopmate_ecommerce_assistant.rag.query_rewrite import (
    EntitySet,
    extract_entities,
    plan_query,
)
from shopmate_ecommerce_assistant.rag.retrieval import DocumentRetriever, RetrievalScope
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
SHOP = UUID("11111111-1111-1111-1111-111111111111")
KB = UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 10, 19, tzinfo=UTC)


# -- entity extraction -----------------------------------------------------


def test_extracts_entities_that_must_be_preserved() -> None:
    entities = extract_entities(
        "订单 DEMO-1001，SKU DEMO-HEAD-001-BLK，预算 300 元，2026-10-01 在新加坡"
    )
    assert entities.order_nos == ("DEMO-1001",)
    assert entities.skus == ("DEMO-HEAD-001-BLK",)
    assert entities.amounts_cents == (30000,)
    assert entities.dates == ("2026-10-01",)
    assert entities.regions == ("SG",)
    assert entities.has_realtime_id() is True


def test_entity_set_reports_missing_values() -> None:
    before = EntitySet(order_nos=("DEMO-1001",), amounts_cents=(30000,))
    after = EntitySet(order_nos=("DEMO-1001",))
    assert after.contains(before) is False
    assert before.contains(after) is True


@pytest.mark.parametrize(
    ("text", "expected_cents"),
    [
        ("我要退货，这单商品 6,000 元", (600000,)),
        ("我要退货，这单 12,000 元", (1200000,)),
        ("预算 1,299 元的耳机保修多久", (129900,)),
        ("预算 1，299 元", (129900,)),
        ("预算 300 元", (30000,)),
    ],
)
def test_grouped_amounts_parse_as_one_value(text: str, expected_cents: tuple[int, ...]) -> None:
    """F1: thousand separators must not split ¥6,000 into "000 元" / 0 cents."""
    assert extract_entities(text).amounts_cents == expected_cents


# -- rewriting rules -------------------------------------------------------


def test_short_complete_question_is_not_rewritten() -> None:
    plan = plan_query("退货运费谁承担", settings=SETTINGS)
    assert plan.strategies == ("none",)
    assert plan.primary_query == "退货运费谁承担"
    assert plan.changed is False
    assert plan.subqueries == ("退货运费谁承担",)
    assert plan.keywords_added == ()


def test_referential_question_without_topic_is_completed_from_history() -> None:
    plan = plan_query(
        "这两款有什么区别",
        history=("预算 300 元以内，适合通勤的降噪耳机",),
        settings=SETTINGS,
        intent="product_compare",
    )
    assert "降噪耳机" in plan.primary_query
    assert "有什么区别" in plan.primary_query
    assert "这两款" not in plan.primary_query
    assert "history_topic" in plan.strategies


def test_pronoun_is_removed_even_when_history_is_not_needed() -> None:
    plan = plan_query(
        "那退货运费谁承担",
        history=("七天无理由退货运费由谁承担？",),
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert plan.primary_query.startswith("退货运费谁承担")
    assert "那退货运费" not in plan.primary_query
    assert "pronoun_stripped" in plan.strategies
    assert plan.keywords_added == (), "去掉指代后已经是短而完整的问题，不再扩展"


def test_identifiers_are_carried_over_and_preserved() -> None:
    plan = plan_query(
        "那个订单呢",
        history=("订单 DEMO-1001 到哪了",),
        settings=SETTINGS,
        intent="shipment",
    )
    assert "DEMO-1001" in plan.primary_query
    assert "entity_carryover" in plan.strategies
    assert plan.entities_preserved is True


def test_order_date_and_region_survive_a_long_policy_question() -> None:
    question = "订单 DEMO-1001 在 2026-10-01 买的，新加坡发货，退款多久到账？"
    plan = plan_query(question, settings=SETTINGS, intent="policy_faq")
    assert plan.primary_query != question
    assert "DEMO-1001" in plan.primary_query
    assert "2026-10-01" in plan.primary_query
    assert "新加坡" in plan.primary_query
    assert plan.entities_preserved is True


def test_grouped_amount_survives_keyword_expansion() -> None:
    """F1: a comma-grouped amount survives filler stripping and keyword expansion."""
    plan = plan_query(
        "预算 1,299 元的耳机保修多久，运费谁承担，发票怎么开",
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert plan.entities_before.amounts_cents == (129900,)
    assert "1,299" in plan.primary_query
    assert plan.entities_preserved is True
    assert len(plan.keywords_added) <= SETTINGS.query_rewrite_max_keywords


def test_sku_survives_expansion() -> None:
    plan = plan_query(
        "DEMO-HEAD-001-BLK 这个 SKU 的保修期是多久",
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert "DEMO-HEAD-001-BLK" in plan.primary_query
    assert plan.entities_preserved is True


def test_product_uuid_survives_a_long_policy_question() -> None:
    """A UUID product id must survive filler stripping, expansion and sub-query splitting."""
    product_id = "3f2b8c1e-9a44-4c21-8f7e-1d2c3b4a5e6f"
    question = (
        f"请问一下，商品 {product_id} 的七天无理由退货政策从什么时候开始计算，退货运费由谁承担？"
    )
    entities = extract_entities(question)
    assert entities.product_ids == (product_id,)
    assert UUID(product_id) == UUID(entities.product_ids[0])

    plan = plan_query(question, settings=SETTINGS, intent="policy_faq")
    assert plan.entities_preserved is True
    assert product_id in plan.primary_query
    assert product_id in plan.core_query
    assert len(plan.keywords_added) <= SETTINGS.query_rewrite_max_keywords
    assert len(plan.subqueries) <= SETTINGS.query_rewrite_max_subqueries
    # the identifier is never re-parsed as a SKU
    assert entities.skus == ()


def test_expansion_bounds_hold_for_a_multi_clause_question() -> None:
    plan = plan_query(
        "如果退货的话退款多久到账，运费谁承担，保修和发票怎么处理，物流怎么查？",
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert len(plan.keywords_added) <= SETTINGS.query_rewrite_max_keywords
    assert len(plan.subqueries) <= SETTINGS.query_rewrite_max_subqueries
    assert plan.strategies != ("none",)


def test_keyword_expansion_is_bounded_and_audited() -> None:
    plan = plan_query(
        "如果退货的话退款多久到账，运费谁承担，保修和发票怎么处理，物流怎么查？",
        settings=Settings(_env_file=None, query_rewrite_max_keywords=4),  # type: ignore[call-arg]
        intent="policy_faq",
    )
    assert 0 < len(plan.keywords_added) <= 4
    assert "keyword_expansion" in plan.strategies
    assert plan.expanded_query.endswith(plan.keywords_added[-1])


def test_subqueries_never_exceed_three() -> None:
    plan = plan_query(
        "七天无理由退货从什么时候开始算，退款多久能到账，退货运费由谁承担呢？",
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert 2 <= len(plan.subqueries) <= 3
    assert "subquery_split" in plan.strategies


def test_filler_is_stripped_from_long_questions() -> None:
    plan = plan_query(
        "请问一下，如果我在新加坡买的东西想退，运费和退款到账时间是怎么规定的？",
        settings=SETTINGS,
        intent="policy_faq",
    )
    assert not plan.primary_query.startswith("请问")
    assert "strip_filler" in plan.strategies
    assert plan.entities_preserved is True


def test_smalltalk_is_never_expanded() -> None:
    plan = plan_query(
        "你好，今天心情不错，随便聊聊", settings=SETTINGS, intent="smalltalk_or_unknown"
    )
    assert plan.keywords_added == ()


# -- embedding path --------------------------------------------------------


def test_rewrite_module_never_embeds_or_uses_bm25() -> None:
    """No second encoder may live in the query path (AGENTS.md §10.4)."""
    source = inspect.getsource(query_rewrite)
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    lowered = " ".join(imported).lower()
    assert "embedding" not in lowered
    assert "milvus" not in lowered
    assert "rank_bm25" not in lowered
    assert "jieba" not in lowered
    assert "embed_query" not in source


class RecordingProvider(FakeHybridEmbeddingProvider):
    """Fake BGE-M3 that counts query forwards."""

    def __init__(self) -> None:
        super().__init__()
        self.query_calls = 0

    def embed_query_hybrid(self, text: str) -> Any:
        self.query_calls += 1
        return super().embed_query_hybrid(text)


class StaticStore:
    """Minimal store that records the hybrid call and its sparse payload."""

    def __init__(self, hits: Sequence[SearchHit]) -> None:
        self.collection = "fake"
        self.hits = list(hits)
        self.calls: list[str] = []
        self.last_sparse: Any = None

    def build_filter(self, **_: Any) -> str:
        return "filter"

    def hybrid_search(self, dense: Any, sparse: Any, **kwargs: Any) -> HybridSearchResult:
        self.calls.append("hybrid_search")
        self.last_sparse = sparse
        return HybridSearchResult(
            hits=tuple(self.hits),
            dense_limit=kwargs["dense_limit"],
            sparse_limit=kwargs["sparse_limit"],
            rrf_k=kwargs["rrf_k"],
        )

    def dense_search(self, dense: Any, **_: Any) -> list[SearchHit]:
        self.calls.append("dense_search")
        return self.hits

    def sparse_search(self, sparse: Any, **_: Any) -> list[SearchHit]:
        self.calls.append("sparse_search")
        return self.hits

    def dense_similarity(self, dense: Any, chunk_ids: Sequence[str]) -> dict[str, float]:
        return {chunk_id: 0.70 for chunk_id in chunk_ids}


def _meta(chunk_id: UUID, index: int) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id,
        shop_id=SHOP,
        knowledge_base_id=KB,
        document_id=uuid4(),
        version_id=uuid4(),
        parent_id=None,
        chunk_index=index,
        heading_path=("七天无理由退货政策（中国大陆）", "运费"),
        page_no=1,
        text="无理由退货运费由消费者承担，质量问题由商城承担。",
        token_count=60,
        is_enabled=True,
        deleted_at=None,
        title="七天无理由退货政策（中国大陆）",
        doc_type="policy",
        locale="zh-CN",
        region="CN",
        document_status="active",
        document_deleted_at=None,
        version="2026.10.1",
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=None,
        parse_status="ready",
        metadata_jsonb={},
    )


class StubModel:
    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.text


@pytest.mark.asyncio
async def test_rewritten_query_uses_the_same_hybrid_retriever_and_provider() -> None:
    chunk_ids = [uuid4() for _ in range(5)]
    hits = [
        SearchHit(
            chunk_id=str(chunk_id),
            score=0.033 - index * 0.001,
            text="无理由退货运费由消费者承担。",
            document_id=str(uuid4()),
            version_id=str(uuid4()),
            knowledge_base_id=str(KB),
            doc_type="policy",
            page_no=1,
            heading_path=("退货政策", "运费"),
            embedding_model="fake-hybrid",
            metadata={"region": "CN", "locale": "zh-CN"},
        )
        for index, chunk_id in enumerate(chunk_ids)
    ]
    metas = {str(chunk_id): _meta(chunk_id, index) for index, chunk_id in enumerate(chunk_ids)}
    store = StaticStore(hits)
    provider = RecordingProvider()

    async def authorizer(ids: Sequence[UUID]) -> dict[UUID, ChunkMetadata]:
        return {chunk_id: metas[str(chunk_id)] for chunk_id in ids if str(chunk_id) in metas}

    retriever = DocumentRetriever(
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            policy_min_evidence_similarity=0.42,
            retrieval_context_token_budget=5000,
        ),
        provider=provider,
        store=store,  # type: ignore[arg-type]
        authorizer=authorizer,
        clock=lambda: NOW,
    )
    service = PolicyQAService(
        retriever=retriever,
        answer_model=StubModel("无理由退货运费由消费者承担[c1]。"),
        settings=SETTINGS,
    )
    plan = plan_query(
        "那退货运费谁承担",
        history=("退货运费谁承担",),
        settings=SETTINGS,
        intent="policy_faq",
    )
    scope = RetrievalScope(
        shop_id=str(SHOP),
        knowledge_base_id=str(KB),
        locale="zh-CN",
        region="CN",
        at=NOW,
    )

    answer = await service.answer("那退货运费谁承担", scope, query_plan=plan)

    assert answer.status == "answered"
    assert provider.query_calls == 1, "改写后的查询只能做一次查询向量前向"
    assert "hybrid_search" in store.calls, "改写后仍必须走 dense+sparse 混合检索"
    assert store.last_sparse, "sparse 支路不得为空，也不得被 BM25 顶替"
    assert answer.retrieval.query == plan.primary_query
    assert answer.audit["query_plan"]["retrieval_query"] == plan.primary_query
    assert answer.audit["query_plan"]["embedding_performed"] is False
    assert answer.audit["embedding"]["model"] == "fake-hybrid"
