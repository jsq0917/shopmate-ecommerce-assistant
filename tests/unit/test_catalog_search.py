"""Unit tests for keyword tokenization, scoring and ranking (no database)."""

from __future__ import annotations

from uuid import uuid4

from shopmate_ecommerce_assistant.domain.catalog.models import (
    ProductHit,
    ProductSnapshot,
    VariantSnapshot,
)
from shopmate_ecommerce_assistant.domain.catalog.search import (
    MAX_QUERY_TOKENS,
    STOPWORD_TOKENS,
    matched_reasons,
    merged_attributes,
    rank_hits,
    score_hit,
    tokenize_query,
)


def _hit(
    *,
    title: str = "声岚 SL-NC300 入耳式降噪耳机",
    category: str = "降噪耳机",
    brand: str | None = "声岚",
    description: str | None = None,
    attributes: dict[str, object] | None = None,
    price_cents: int = 29900,
) -> ProductHit:
    product_id = uuid4()
    return ProductHit(
        product=ProductSnapshot(
            id=product_id,
            title=title,
            description=description,
            brand=brand,
            category=category,
            attributes=attributes or {},
            status="active",
            is_synthetic=True,
        ),
        variant=VariantSnapshot(
            id=uuid4(),
            product_id=product_id,
            sku="SM-DEMO-01",
            title=f"{title} · 曜石黑",
            attributes={"color": "曜石黑"},
            price_cents=price_cents,
            currency="CNY",
            status="active",
            available_qty=10,
        ),
    )


def test_tokenize_chinese_run_into_bigrams() -> None:
    assert tokenize_query("降噪耳机") == ("降噪", "噪耳", "耳机")


def test_tokenize_mixes_latin_and_chinese() -> None:
    assert tokenize_query("SL-NC700 耳机") == ("sl", "nc700", "耳机")


def test_tokenize_drops_conversational_stopwords() -> None:
    assert tokenize_query("预算 适合 推荐 想要") == ()
    assert "预算" in STOPWORD_TOKENS


def test_tokenize_is_bounded() -> None:
    tokens = tokenize_query("降噪耳机" * 40)

    assert len(tokens) <= MAX_QUERY_TOKENS
    assert len(set(tokens)) == len(tokens)


def test_score_prefers_title_then_metadata() -> None:
    hit = _hit()
    title_match = score_hit(("降噪",), hit)
    metadata_match = score_hit(("声岚", "降噪耳机"), _hit(title="SL-NC300"))

    assert title_match.title_hit is True
    assert title_match.score >= 3
    assert metadata_match.category_or_brand_hit is True
    assert metadata_match.score >= 4


def test_score_matches_attributes_and_description_separately() -> None:
    attribute_hit = score_hit(("battery_hours",), _hit(attributes={"battery_hours": 40}))
    description_hit = score_hit(("通勤",), _hit(description="适合通勤与长时间办公佩戴。"))

    assert attribute_hit.attribute_hit is True
    assert attribute_hit.title_hit is False
    assert description_hit.description_hit is True
    assert description_hit.score == 1


def test_rank_hits_orders_by_relevance_then_price() -> None:
    strong = _hit(title="声岚 SL-NC300 降噪耳机", price_cents=39900)
    weak = _hit(title="光影 CAM-2K", category="摄像头", description="支持降噪？", price_cents=9900)
    cheap_same_score = _hit(title="声岚 SL-NC100 降噪耳机", price_cents=19900)

    ranked = rank_hits([weak, strong, cheap_same_score], ("降噪",))

    assert [item.hit.variant.price_cents for item in ranked] == [19900, 39900, 9900]
    assert ranked[-1].match.score < ranked[0].match.score


def test_rank_hits_is_stable_without_tokens() -> None:
    expensive = _hit(price_cents=30000)
    cheap = _hit(price_cents=10000)

    ranked = rank_hits([expensive, cheap], ())

    assert ranked[0].hit.variant.price_cents == 10000
    assert all(item.match.score == 0 for item in ranked)


def test_merged_attributes_lets_variant_override_product() -> None:
    merged = merged_attributes({"color": "默认", "battery_hours": 24}, {"color": "曜石黑"})

    assert merged == {"color": "曜石黑", "battery_hours": 24}


def test_matched_reasons_are_explicit_and_never_empty() -> None:
    assert matched_reasons(
        match=None,
        category_filter=False,
        brand_filter=False,
        budget_filter=False,
        attribute_filter=False,
        in_stock=False,
    ) == ["在售商品"]

    reasons = matched_reasons(
        match=score_hit(("降噪",), _hit()),
        category_filter=True,
        brand_filter=False,
        budget_filter=True,
        attribute_filter=True,
        in_stock=True,
    )
    assert reasons == ["关键词匹配", "类目匹配", "预算内", "属性匹配", "有货"]
