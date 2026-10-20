"""Keyword tokenization and deterministic ranking for ``search_products``.

This is deliberately a *lexical* filter, not a semantic retriever: the query is split
into Chinese bigrams and ASCII words, then matched as bound ``ILIKE`` parameters against
title, category, brand, attributes and description. PostgreSQL (stage 5) is the only
source of price and stock; ranking never invents facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shopmate_ecommerce_assistant.domain.catalog.models import ProductHit

MAX_QUERY_TOKENS = 20
MIN_KEYWORD_SCORE = 2
_CJK_RUN = re.compile(r"[0-9a-z]+|[\u4e00-\u9fff]+")

# Conversational filler that carries no product signal. Descriptions are full of these,
# so keeping them would make unrelated products "match" on words like 适合.
STOPWORD_TOKENS = frozenset(
    {
        "适合",
        "预算",
        "以内",
        "左右",
        "推荐",
        "需要",
        "想要",
        "请问",
        "可以",
        "什么",
        "怎么",
        "多少",
        "有没有",
        "一个",
    }
)


@dataclass(frozen=True, slots=True)
class MatchScore:
    """How a product matched the keyword tokens, and which fields were hit."""

    score: int
    title_hit: bool
    category_or_brand_hit: bool
    attribute_hit: bool
    description_hit: bool

    @property
    def any_hit(self) -> bool:
        return (
            self.title_hit
            or self.category_or_brand_hit
            or self.attribute_hit
            or self.description_hit
        )


@dataclass(frozen=True, slots=True)
class RankedHit:
    """A product hit plus its keyword score, ready to be rendered as a card."""

    hit: ProductHit
    match: MatchScore


def tokenize_query(query: str) -> tuple[str, ...]:
    """Split a Chinese/English query into stable, bounded search tokens.

    Chinese runs longer than three characters are expanded into overlapping bigrams,
    because there is no whitespace to segment on and a whole-sentence ``ILIKE`` would
    match nothing. Duplicates are removed while preserving order.
    """
    tokens: list[str] = []
    for run in _CJK_RUN.findall(query.strip().lower()):
        if run[0].isascii():
            if len(run) >= 2 or run.isdigit():
                tokens.append(run)
            continue
        if len(run) <= 3:
            tokens.append(run)
        else:
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))

    unique: list[str] = []
    for token in tokens:
        if token in STOPWORD_TOKENS:
            continue
        if token not in unique:
            unique.append(token)
        if len(unique) >= MAX_QUERY_TOKENS:
            break
    return tuple(unique)


def merged_attributes(
    product_attributes: Mapping[str, Any], variant_attributes: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge product and SKU attributes; the SKU wins on shared keys (e.g. colour)."""
    merged = dict(product_attributes)
    merged.update(variant_attributes)
    return merged


def score_hit(tokens: Sequence[str], hit: ProductHit) -> MatchScore:
    """Score one product/variant pair against the query tokens."""
    title = hit.product.title.lower()
    metadata = f"{hit.product.category} {hit.product.brand or ''}".lower()
    attributes = json.dumps(
        merged_attributes(hit.product.attributes, hit.variant.attributes),
        ensure_ascii=False,
        default=str,
    ).lower()
    description = (hit.product.description or "").lower()
    variant_text = f"{hit.variant.title} {hit.variant.sku}".lower()

    score = 0
    title_hit = category_or_brand_hit = attribute_hit = description_hit = False
    for token in tokens:
        needle = token.lower()
        if not needle:
            continue
        if needle in title or needle in variant_text:
            title_hit = True
            score += 3
        elif needle in metadata:
            category_or_brand_hit = True
            score += 2
        elif needle in attributes:
            attribute_hit = True
            score += 1
        elif needle in description:
            description_hit = True
            score += 1

    return MatchScore(
        score=score,
        title_hit=title_hit,
        category_or_brand_hit=category_or_brand_hit,
        attribute_hit=attribute_hit,
        description_hit=description_hit,
    )


def rank_hits(hits: Sequence[ProductHit], tokens: Sequence[str]) -> list[RankedHit]:
    """Score and sort hits by relevance, then price, then title (stable and repeatable)."""
    if not tokens:
        neutral = MatchScore(0, False, False, False, False)
        ranked = [RankedHit(hit=hit, match=neutral) for hit in hits]
    else:
        ranked = [RankedHit(hit=hit, match=score_hit(tokens, hit)) for hit in hits]
    ranked.sort(
        key=lambda item: (
            -item.match.score,
            item.hit.variant.price_cents,
            item.hit.product.title,
            str(item.hit.product.id),
        )
    )
    return ranked


def matched_reasons(
    *,
    match: MatchScore | None,
    category_filter: bool,
    brand_filter: bool,
    budget_filter: bool,
    attribute_filter: bool,
    in_stock: bool,
) -> list[str]:
    """Explain, in Chinese, why a card is in the result set."""
    reasons: list[str] = []
    if match is not None and match.any_hit:
        reasons.append("关键词匹配")
    if category_filter:
        reasons.append("类目匹配")
    if brand_filter:
        reasons.append("品牌匹配")
    if budget_filter:
        reasons.append("预算内")
    if attribute_filter:
        reasons.append("属性匹配")
    if in_stock:
        reasons.append("有货")
    return reasons or ["在售商品"]
