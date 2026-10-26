"""Deterministic query understanding: catalog resolution and stock wording.

``resolve_catalog_item`` exists because the contract's read tools take UUIDs
(``get_product_detail`` / ``check_stock`` / ``compare_products``) while shoppers type
names. Stage 13 measured what happens without it: 9 fact turns and 12 comparison turns
never reached those tools. The rule under test is the safety property — resolve only when
the answer is unique, otherwise return ``None`` so the caller keeps its honest fallback.
"""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.agents.query_understanding import (
    best_overlap_item,
    is_stock_question,
    model_tokens,
    resolve_catalog_item,
    split_compare_sides,
)


def _item(title: str, **extra: str) -> dict[str, str]:
    return {"title": title, **extra}


NC300 = _item("声岚 SL-NC300 入耳式降噪耳机 · 云雾白", product_id="p-nc300")
BUDS_AIR = _item("声岚 SL-BUDS Air 真无线蓝牙耳机 · 云雾白", product_id="p-air")
BUDS_LITE = _item("声岚 SL-BUDS Lite 真无线耳机 · 碳黑", product_id="p-lite")
KC87 = _item("键川 KC87 三模机械键盘 · 深空灰", product_id="p-kc87")
KC104 = _item("键川 KC104 全尺寸机械键盘 · 深空灰", product_id="p-kc104")
KW200 = _item("键川 KW200 无线薄膜键盘 · 雾银白", product_id="p-kw200")
KC68 = _item("键川 KC68 便携机械键盘 · 云雾白", product_id="p-kc68")

#: The catalogue order the keyboard searches really return: the membrane keyboard
#: tops both "无线键盘" and "机械键盘" expansions.
KEYBOARDS = [KW200, KC68, KC87, KC104]
PB10000 = _item("速派 PB10000 移动电源 · 云雾白", product_id="p-pb10000")
PB20000 = _item("速派 PB20000 移动电源 · 深空灰", product_id="p-pb20000")
QC30 = _item("速派 QC30 快充充电器", product_id="p-qc30")
WC15 = _item("速派 WC15 无线充电器", product_id="p-wc15")


def test_model_tokens_read_the_code_a_shopper_types() -> None:
    assert model_tokens("声岚 SL-BUDS Air 真无线蓝牙耳机 卖多少钱？") == ("sl-buds", "air")
    assert model_tokens("键川 KC87 还有货吗") == ("kc87",)
    assert model_tokens("光影 GM-X2 的续航") == ("gm-x2",)
    # Chinese-only wording carries no model code at all.
    assert model_tokens("机械键盘多少钱") == ()


@pytest.mark.parametrize(
    ("text", "items", "expected"),
    [
        # 1. every model token must appear: "Air" must not resolve to "Lite" and vice versa
        ("声岚 SL-BUDS Air 真无线蓝牙耳机 卖多少钱？", [BUDS_AIR, BUDS_LITE], "p-air"),
        ("声岚 SL-BUDS Lite 真无线耳机 还有货吗？", [BUDS_AIR, BUDS_LITE], "p-lite"),
        ("声岚 SL-NC300 入耳式降噪耳机 现在还有货吗？", [NC300, BUDS_AIR], "p-nc300"),
        # 2. an explicit product id / sku in the text wins over wording
        ("声岚 SL-BUDS Air 和别的比一下 p-lite", [BUDS_AIR, BUDS_LITE], "p-lite"),
        # 3. a category word resolves only when it is unique
        ("机械键盘多少钱？", [KC87, KC104], None),
        ("机械键盘多少钱？", [KC87, BUDS_AIR], "p-kc87"),
        # 4. nothing to go on → None (the caller shows cards instead of guessing)
        ("这个多少钱？", [NC300, BUDS_AIR], None),
        ("", [NC300], None),
        ("声岚 SL-BUDS Pro 卖多少钱？", [BUDS_AIR, BUDS_LITE], None),
    ],
)
def test_resolve_catalog_item(text: str, items: list[dict[str, str]], expected: str | None) -> None:
    resolved = resolve_catalog_item(text, items)
    assert (resolved or {}).get("product_id") == expected


def test_resolve_catalog_item_accepts_extra_categories() -> None:
    """The caller may pass category words it already inferred (e.g. from the router)."""
    resolved = resolve_catalog_item("那个键盘多少钱", [KC87, BUDS_AIR], categories=("机械键盘",))
    assert resolved is KC87


@pytest.mark.parametrize(
    ("text", "items", "expected"),
    [
        # eval-136: the membrane keyboard tops *both* keyboard expansions, so a
        # blind items[0] would compare one product with itself. Each operand's
        # distinguishing word ("无线" / "机械") picks its representative.
        ("无线键盘", KEYBOARDS, "p-kw200"),
        ("机械键盘", KEYBOARDS, "p-kc68"),
        ("薄膜键盘", KEYBOARDS, "p-kw200"),
        # no distinguishing word: the search ranking stands (eval-134)
        ("移动电源", [PB10000, PB20000], "p-pb10000"),
        ("充电器", [QC30, WC15], "p-qc30"),
        # nothing to choose from
        ("机械键盘", [], None),
    ],
)
def test_best_overlap_item(text: str, items: list[dict[str, str]], expected: str | None) -> None:
    assert (best_overlap_item(text, items) or {}).get("product_id") == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("声岚 SL-NC300 现在还有货吗？", True),
        ("蓝牙音箱有现货吗", True),
        ("这个是不是缺货了", True),
        ("库存还有多少", True),
        ("键川 KC87 卖多少钱？", False),
        ("智能手表续航多久？", False),
        ("能退吗", False),
    ],
)
def test_is_stock_question(text: str, expected: bool) -> None:
    assert is_stock_question(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # the 12 business comparison cases, minus their question tails
        (
            "声岚 SL-NC700 头戴式主动降噪耳机 和 声岚 SL-NC500 轻量头戴降噪耳机 有什么区别？",
            ("声岚 SL-NC700 头戴式主动降噪耳机", "声岚 SL-NC500 轻量头戴降噪耳机"),
        ),
        ("键川 KC87 和 键川 KC104 对比一下", ("键川 KC87", "键川 KC104")),
        ("移动电源和充电器哪个更值得买？", ("移动电源", "充电器")),
        ("无线键盘和机械键盘有什么区别？", ("无线键盘", "机械键盘")),
        # "对比" is a verb too: it must not be used as a separator
        (
            "声岚 SL-BUDS Air 和 声岚 SL-BUDS Lite 对比一下",
            ("声岚 SL-BUDS Air", "声岚 SL-BUDS Lite"),
        ),
        # not a clean two-operand comparison → keep the clarification
        ("这两款哪个好", None),
        ("声岚 SL-BUDS Air 有什么区别？", None),
        ("声岚 SL-BUDS Air 和 声岚 SL-BUDS Air 有什么区别？", None),
        ("", None),
    ],
)
def test_split_compare_sides(text: str, expected: tuple[str, str] | None) -> None:
    assert split_compare_sides(text) == expected
