"""FAQ high-confidence matching and version-keyed Redis cache behaviour."""

from __future__ import annotations

import fnmatch
import json
from datetime import UTC, datetime

import pytest

from shopmate_ecommerce_assistant.agents.router import route_intent
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.faq import (
    CachedFaqAnswer,
    FaqAnswerCache,
    FaqCacheScope,
    FaqIndex,
    FaqRecord,
    FaqService,
    load_faq_index,
    normalize_question,
)

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
SHOP = "11111111-1111-1111-1111-111111111111"
OTHER_SHOP = "22222222-2222-2222-2222-222222222222"
KB = "33333333-3333-3333-3333-333333333333"


def _scope(**overrides: str) -> FaqCacheScope:
    payload = {
        "shop_id": SHOP,
        "region": "CN",
        "locale": "zh-CN",
        "knowledge_version": "kv-20261001",
        "knowledge_base_id": KB,
    }
    payload.update(overrides)
    return FaqCacheScope(**payload)


def _citations() -> list[dict[str, str]]:
    return [
        {
            "label": "c1",
            "citation_id": "cit_abc",
            "title": "七天无理由退货政策（中国大陆）",
            "version": "2026.10.1",
        }
    ]


def _answer(
    text: str = "无理由退货运费由消费者承担[c1]。",
    *,
    version: str = "kv-20261001",
) -> CachedFaqAnswer:
    return CachedFaqAnswer(
        question="退货运费谁承担？",
        answer=text,
        citation_labels=("c1",),
        citations=tuple(_citations()),
        knowledge_version=version,
        intent="policy_faq",
        created_at=NOW.isoformat(),
    )


class MemoryBackend:
    """Dict-backed Redis double with failure injection."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []
        self.fail = False

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise RuntimeError("redis down")
        return self.data.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        if self.fail:
            raise RuntimeError("redis down")
        self.data[key] = value
        self.ttls[key] = ex

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.data.pop(key, None)

    async def keys(self, pattern: str) -> list[str]:
        return [key for key in list(self.data) if fnmatch.fnmatch(key, pattern)]


RECORDS = (
    FaqRecord(
        faq_id="faq-001",
        question="退货运费谁承担？",
        answer="无理由退货运费由消费者承担，质量问题由商城承担。",
        category="退货",
        region="CN",
        locale="zh-CN",
        policy_document_key="return-policy-cn",
    ),
    FaqRecord(
        faq_id="faq-005",
        question="退款多久能到账？",
        answer="验收通过后一至七个工作日原路退回。",
        category="退款",
        region="CN",
        locale="zh-CN",
        policy_document_key="refund-timeline",
    ),
    FaqRecord(
        faq_id="faq-sg-001",
        question="新加坡订单退货期限是多久？",
        answer="十五日内。",
        category="退货",
        region="SG",
        locale="zh-CN",
        policy_document_key="return-policy-sg",
    ),
)


def _index() -> FaqIndex:
    return FaqIndex(RECORDS)


# -- matching --------------------------------------------------------------


def test_normalisation_removes_fillers_punctuation_and_spaces() -> None:
    assert normalize_question("请问 退货运费谁承担？") == normalize_question("退货运费谁承担")


def test_exact_match_is_full_confidence() -> None:
    match = _index().match("请问退货运费谁承担？", region="CN", locale="zh-CN")
    assert match.matched is True
    assert match.confidence == 1.0
    assert match.record is not None
    assert match.record.faq_id == "faq-001"


def test_high_similarity_variant_is_accepted() -> None:
    match = _index().match("退货运费谁承担呀", region="CN", locale="zh-CN")
    assert match.matched is True
    assert match.reason == "fuzzy"
    assert match.confidence >= SETTINGS.faq_min_match_confidence


def test_unrelated_question_is_rejected() -> None:
    match = _index().match("退货运费怎么计算", region="CN", locale="zh-CN")
    assert match.matched is False
    assert match.reason == "below_threshold"


def test_region_mismatch_never_falls_back_to_another_region() -> None:
    match = _index().match("退货运费谁承担？", region="SG", locale="zh-CN")
    assert match.matched is False
    assert match.reason == "region_mismatch"


def test_curated_faq_file_loads_without_skipping_rows() -> None:
    index = load_faq_index()
    assert len(index) >= 40
    assert index.skipped == 0


# -- cache key and lifecycle ----------------------------------------------


def test_cache_key_contains_every_required_dimension() -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    key = cache.build_key("退货运费谁承担", scope)
    assert key.startswith("shopmate:faq:v1:")
    assert f":{SHOP}:" in key
    assert ":CN:zh-CN:" in key
    assert f":{KB}:" in key
    assert ":kv-20261001:" in key
    assert cache.build_key("退货运费谁承担？", scope) == key
    assert cache.build_key("退款多久能到账", scope) != key


@pytest.mark.asyncio
async def test_put_then_get_returns_citations_and_ttl() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()

    write = await cache.put(
        "退货运费谁承担",
        scope,
        _answer(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
    )
    assert write.stored is True
    assert backend.ttls[write.key] == SETTINGS.faq_cache_ttl_seconds

    lookup = await cache.get("退货运费谁承担", scope)
    assert lookup.hit is True
    assert lookup.citations[0]["label"] == "c1"


@pytest.mark.asyncio
async def test_new_knowledge_version_misses_the_old_entry() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    await cache.put(
        "退货运费谁承担",
        _scope(),
        _answer(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
    )

    new_scope = _scope(knowledge_version="kv-20261101")
    assert cache.build_key("退货运费谁承担", new_scope) != cache.build_key(
        "退货运费谁承担", _scope()
    )
    lookup = await cache.get("退货运费谁承担", new_scope)
    assert lookup.hit is False
    assert lookup.reason == "not_found"


@pytest.mark.asyncio
async def test_payload_with_old_version_is_rejected_and_deleted() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    key = cache.build_key("退货运费谁承担", scope)
    backend.data[key] = _answer(version="kv-old").to_payload()

    lookup = await cache.get("退货运费谁承担", scope)

    assert lookup.hit is False
    assert lookup.reason == "stale_version"
    assert key not in backend.data


@pytest.mark.asyncio
async def test_corrupt_payload_is_deleted() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    key = cache.build_key("退货运费谁承担", scope)
    backend.data[key] = "{not-json"

    lookup = await cache.get("退货运费谁承担", scope)
    assert lookup.hit is False
    assert lookup.reason == "corrupt"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "risk", "evidence", "answer", "expected"),
    [
        ("product_fact", "low", True, _answer(), "intent_not_cacheable"),
        ("order_status", "low", True, _answer(), "intent_not_cacheable"),
        ("shipment", "low", True, _answer(), "intent_not_cacheable"),
        ("policy_faq", "high", True, _answer(), "risk_not_cacheable"),
        ("policy_faq", "medium", True, _answer(), "risk_not_cacheable"),
        ("policy_faq", "low", False, _answer(), "no_evidence"),
        (
            "policy_faq",
            "low",
            True,
            CachedFaqAnswer(
                question="q",
                answer="a",
                citation_labels=(),
                citations=(),
                knowledge_version="kv-20261001",
                intent="policy_faq",
                created_at=NOW.isoformat(),
            ),
            "no_citations",
        ),
    ],
)
async def test_non_cacheable_answers_are_rejected(
    intent: str, risk: str, evidence: bool, answer: CachedFaqAnswer, expected: str
) -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    write = await cache.put(
        "退货运费谁承担",
        _scope(),
        answer,
        intent=intent,
        risk_level=risk,
        evidence_sufficient=evidence,
    )
    assert write.stored is False
    assert write.reason == expected


@pytest.mark.asyncio
async def test_injection_flagged_answers_are_not_cached() -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    write = await cache.put(
        "退货运费谁承担",
        _scope(),
        _answer(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        injection_detected=True,
    )
    assert write.stored is False
    assert write.reason == "injection_flagged"


@pytest.mark.asyncio
async def test_cache_outage_degrades_to_a_miss() -> None:
    backend = MemoryBackend()
    backend.fail = True
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)

    lookup = await cache.get("退货运费谁承担", _scope())
    write = await cache.put(
        "退货运费谁承担",
        _scope(),
        _answer(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
    )
    assert lookup.hit is False
    assert lookup.reason == "unavailable"
    assert write.stored is False
    assert write.reason == "unavailable"


@pytest.mark.asyncio
async def test_invalidate_shop_only_removes_that_shop() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    for question in ("退货运费谁承担", "退款多久能到账"):
        await cache.put(
            question,
            _scope(),
            _answer(),
            intent="policy_faq",
            risk_level="low",
            evidence_sufficient=True,
        )
    await cache.put(
        "退货运费谁承担",
        _scope(shop_id=OTHER_SHOP),
        _answer(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
    )

    deleted = await cache.invalidate_shop(SHOP)

    assert deleted == 2
    assert all(f":{SHOP}:" not in key for key in backend.data)
    assert any(f":{OTHER_SHOP}:" in key for key in backend.data)


# -- service ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_stores_and_serves_a_guarded_answer() -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()

    write = await service.remember(
        "退货运费谁承担",
        scope=scope,
        answer="无理由退货运费由消费者承担[c1]。",
        citations=_citations(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        route_cache_eligible=True,
    )
    lookup = await service.lookup("退货运费谁承担", scope=scope)

    assert write.stored is True
    assert lookup.cache.hit is True
    assert lookup.answer is not None
    assert lookup.answer.faq_id == "faq-001"
    assert lookup.citations[0]["label"] == "c1"
    assert lookup.guard is not None
    assert lookup.guard.allowed is True


@pytest.mark.asyncio
async def test_two_phrasings_share_the_canonical_cache_key() -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    await service.remember(
        "退货运费谁承担",
        scope=scope,
        answer="无理由退货运费由消费者承担[c1]。",
        citations=_citations(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        route_cache_eligible=True,
    )

    lookup = await service.lookup("退货运费谁承担呀", scope=scope)

    assert lookup.cache.hit is True
    assert lookup.effective_question == "退货运费谁承担？"


@pytest.mark.asyncio
async def test_cached_money_promise_is_rejected_by_the_output_guard() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    await service.remember(
        "退货运费谁承担",
        scope=scope,
        answer="已为您退款[c1]。",
        citations=_citations(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        route_cache_eligible=True,
    )

    lookup = await service.lookup("退货运费谁承担", scope=scope)

    assert lookup.cache.hit is False
    assert lookup.cache.reason == "guard_rejected"
    assert backend.data == {}


@pytest.mark.asyncio
async def test_cached_answer_with_pii_is_rejected() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)
    scope = _scope()
    await service.remember(
        "退货运费谁承担",
        scope=scope,
        answer="请联系 13812345678 处理[c1]。",
        citations=_citations(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        route_cache_eligible=True,
    )

    lookup = await service.lookup("退货运费谁承担", scope=scope)

    assert lookup.cache.hit is False
    assert lookup.cache.reason == "guard_rejected"


@pytest.mark.asyncio
async def test_service_without_a_match_uses_the_raw_question() -> None:
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)

    lookup = await service.lookup("门店在哪里", scope=_scope())

    assert lookup.match.matched is False
    assert lookup.effective_question == "门店在哪里"
    assert lookup.cache.hit is False


def test_payload_round_trip_is_json_safe() -> None:
    payload = json.loads(_answer().to_payload())
    assert payload["citation_labels"] == ["c1"]
    assert payload["knowledge_version"] == "kv-20261001"


# -- fail-closed service gate (stage-8 acceptance defect G4) ---------------


@pytest.mark.asyncio
async def test_route_ineligible_write_is_rejected() -> None:
    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)

    write = await service.remember(
        "退货运费谁承担",
        scope=_scope(),
        answer="无理由退货运费由消费者承担[c1]。",
        citations=_citations(),
        intent="policy_faq",
        risk_level="low",
        evidence_sufficient=True,
        route_cache_eligible=False,
    )

    assert write.stored is False
    assert write.reason == "route_not_cacheable"
    assert backend.data == {}


@pytest.mark.asyncio
async def test_low_confidence_policy_question_is_not_cached() -> None:
    """A policy turn below the confidence gate must never reach Redis."""
    strict = Settings(_env_file=None, intent_min_confidence=0.80)  # type: ignore[call-arg]
    route = route_intent("退货政策", settings=strict)
    assert route.intent.value == "policy_faq"
    assert route.cache_eligible is False

    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=strict, clock=lambda: NOW)
    write = await service.remember(
        "退货政策",
        scope=_scope(),
        answer="相关政策如下[c1]。",
        citations=_citations(),
        intent=route.intent.value,
        risk_level=route.risk.level.value,
        evidence_sufficient=True,
        route_cache_eligible=route.cache_eligible,
    )

    assert write.stored is False
    assert write.reason == "route_not_cacheable"
    assert backend.data == {}


@pytest.mark.asyncio
async def test_policy_question_with_an_order_number_is_not_cached() -> None:
    route = route_intent("订单 DEMO-1001 的退款政策是什么", settings=SETTINGS)
    assert route.intent.value == "policy_faq"
    assert route.cache_eligible is False

    backend = MemoryBackend()
    cache = FaqAnswerCache(backend, settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)
    write = await service.remember(
        "订单 DEMO-1001 的退款政策是什么",
        scope=_scope(),
        answer="验收通过后一至七个工作日原路退回[c1]。",
        citations=_citations(),
        intent=route.intent.value,
        risk_level=route.risk.level.value,
        evidence_sufficient=True,
        route_cache_eligible=route.cache_eligible,
    )

    assert write.stored is False
    assert write.reason == "route_not_cacheable"
    assert backend.data == {}


@pytest.mark.asyncio
async def test_cacheability_inputs_have_no_defaults() -> None:
    """Omitting a cacheability input must be a TypeError, never a silent default."""
    cache = FaqAnswerCache(MemoryBackend(), settings=SETTINGS, clock=lambda: NOW)
    service = FaqService(_index(), cache, settings=SETTINGS, clock=lambda: NOW)

    for missing in ("intent", "risk_level", "evidence_sufficient", "route_cache_eligible"):
        kwargs: dict[str, object] = {
            "scope": _scope(),
            "answer": "无理由退货运费由消费者承担[c1]。",
            "citations": _citations(),
            "intent": "policy_faq",
            "risk_level": "low",
            "evidence_sufficient": True,
            "route_cache_eligible": True,
        }
        kwargs.pop(missing)
        with pytest.raises(TypeError):
            await service.remember("退货运费谁承担", **kwargs)  # type: ignore[arg-type]
