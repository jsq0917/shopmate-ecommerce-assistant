"""Deterministic query understanding for the chat path.

The router decides *which* path a turn takes; this module extracts the business arguments
that path needs, so the planner never has to guess:

* a budget upper bound ("预算 300 以内" / "不超过 300 元") - the catalog filter otherwise
  ignores the number and returns items above the stated budget;
* catalog synonyms ("跑鞋" → "跑步鞋") that the bigram matcher cannot bridge;
* a return reason code inferred from the shopper's wording;
* which order line the shopper is talking about.

Everything here is rule-based and returns ``None`` when unsure: an honest clarification is
better than a confident wrong argument.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from shopmate_ecommerce_assistant.db.models.enums import ReturnReasonCode

#: ``预算 300`` / ``300 元以内`` / ``不超过 300`` / ``300 以下`` / ``300 左右``.
_BUDGET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"预算\s*(?:为|是|在)?\s*(\d{2,6})"),
    re.compile(r"(\d{2,6})\s*(?:元|块)?\s*(?:以内|以下|之内|左右|内)"),
    re.compile(r"不超过\s*(\d{2,6})"),
    re.compile(r"最高\s*(\d{2,6})"),
    re.compile(r"别超过\s*(\d{2,6})"),
    re.compile(r"(\d{2,6})\s*元?\s*以内的"),
)

#: Product-line synonyms. Keys are what shoppers type, values are catalog words to append
#: to the search query (never replace the original text: the original may still match).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "跑鞋": ("跑步鞋",),
    "跑步": ("跑步鞋",),
    "运动鞋": ("跑步鞋",),
    "球鞋": ("运动鞋",),
    "鞋子": ("跑步鞋", "运动鞋"),
    "背包": ("双肩包",),
    "书包": ("双肩包",),
    "电脑包": ("双肩包",),
    "行李箱": ("行李箱",),
    "拉杆箱": ("行李箱",),
    "水杯": ("保温杯",),
    "杯子": ("保温杯",),
    "保温壶": ("保温杯",),
    "枕头": ("枕头",),
    "四件套": ("床品四件套",),
    "床单": ("床品四件套",),
    "台灯": ("台灯",),
    "护眼灯": ("台灯",),
    "炸锅": ("空气炸锅",),
    "咖啡机": ("咖啡机",),
    "破壁": ("料理机",),
    "榨汁": ("料理机",),
    "牙刷": ("电动牙刷",),
    "吹风": ("吹风机",),
    "洗发": ("洗发水",),
    "面膜": ("面膜",),
    "护手霜": ("护手霜",),
    "瑜伽": ("瑜伽垫",),
    "哑铃": ("哑铃",),
    "登山": ("登山包",),
    "徒步": ("登山包",),
    "猫粮": ("猫粮",),
    "猫砂": ("猫砂",),
    "咖啡豆": ("咖啡",),
    "挂耳": ("咖啡",),
    "坚果": ("坚果",),
    "显示器": ("显示器",),
    "手环": ("智能手环",),
    "充电宝": ("移动电源",),
    "移动电源": ("移动电源",),
    "键盘": ("机械键盘", "薄膜键盘"),
    "鼠标": ("鼠标",),
    "降噪": ("降噪耳机",),
    "耳机": ("耳机",),
    "音响": ("蓝牙音箱",),
    "音箱": ("蓝牙音箱",),
    "手表": ("智能手表",),
    "摄像头": ("摄像头",),
    "支架": ("手机支架",),
    "数据线": ("数据线",),
    "充电器": ("充电器",),
    "充电头": ("充电器",),
    "T恤": ("T恤",),
    "短袖": ("T恤",),
    "卫衣": ("卫衣",),
    "帽衫": ("卫衣",),
}

_REASON_RULES: tuple[tuple[ReturnReasonCode, re.Pattern[str]], ...] = (
    (
        ReturnReasonCode.DAMAGED_ON_ARRIVAL,
        re.compile(r"破损|损坏|压坏|碎了|破裂|漏了|漏液|坏(?:了|掉)"),
    ),
    (ReturnReasonCode.WRONG_ITEM, re.compile(r"发错|错货|发的不对|不是我(?:买|要)的|少发")),
    (ReturnReasonCode.QUALITY_ISSUE, re.compile(r"质量|瑕疵|异味|做工|色差|不好用|有毛病")),
    (
        ReturnReasonCode.SIZE_OR_FIT,
        re.compile(r"尺码|码数|大小不合|不合脚|穿不上|太小|太大|偏小|偏大|不合身"),
    ),
    (
        ReturnReasonCode.NO_LONGER_NEEDED,
        re.compile(r"不想要|不喜欢|不需要|买多|买错|无理由|七天无理由|不打算要"),
    ),
)

_CJK = re.compile(r"[\u4e00-\u9fff]+")


def extract_budget_cents(text: str) -> int | None:
    """Return the shopper's stated budget ceiling in cents, or ``None``.

    Only explicit budget wording counts. A bare price mention ("这个多少钱") is a question,
    not a ceiling, and must not silently filter the catalog.
    """
    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(text)
        if match:
            yuan = int(match.group(1))
            if 1 <= yuan <= 1_000_000:
                return yuan * 100
    return None


def expand_query(text: str) -> str:
    """Append catalog synonyms so a colloquial word can reach the product title."""
    extras: list[str] = []
    for trigger, targets in SYNONYMS.items():
        if trigger in text:
            for target in targets:
                if target not in text and target not in extras:
                    extras.append(target)
    if not extras:
        return text
    return f"{text} {' '.join(extras)}"


def category_terms(text: str) -> tuple[str, ...]:
    """Return catalog words implied by the text, most specific first.

    Used to drop cards that only matched a scenario word: "适合通勤的降噪耳机" should not
    return a commuter backpack just because its description also says 通勤.
    """
    terms: list[str] = []
    for trigger, targets in SYNONYMS.items():
        if trigger in text:
            for target in targets:
                if target not in terms:
                    terms.append(target)
    return tuple(terms)


def infer_return_reason(text: str) -> ReturnReasonCode | None:
    """Return the reason code implied by the wording, or ``None`` when ambiguous."""
    for code, pattern in _REASON_RULES:
        if pattern.search(text):
            return code
    return None


def _bigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for run in _CJK.findall(text):
        if len(run) <= 2:
            grams.add(run)
        else:
            grams.update(run[index : index + 2] for index in range(len(run) - 1))
    return grams


def match_line[T](text: str, lines: Sequence[tuple[T, str, str]]) -> T | None:
    """Pick the order line the shopper means.

    Args:
        text: the shopper's message.
        lines: ``(key, sku, title)`` triples of the candidate order lines.

    Returns:
        The unique best-matching key, or ``None`` when nothing or several lines match.
    """
    if not text or not lines:
        return None
    if len(lines) == 1:
        return lines[0][0]
    lowered = text.lower()
    for key, sku, _title in lines:
        if sku and sku.lower() in lowered:
            return key

    wanted = _bigrams(text)
    scored: list[tuple[int, T]] = []
    for key, _sku, title in lines:
        overlap = len(wanted & _bigrams(title))
        if overlap > 0:
            scored.append((overlap, key))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


# -- catalog resolution -------------------------------------------------------
#
# ``get_product_detail`` / ``check_stock`` / ``compare_products`` all take UUIDs, but
# shoppers name products ("声岚 SL-BUDS Air 卖多少钱"). Stage 13 measured the cost of that
# gap: 9 fact questions and 12 comparison turns degraded to a search list or a
# clarification. Resolution is a *lookup* step, never an answer: when it is not unique the
# caller keeps its existing fallback.

#: Model codes as shoppers type them: ``SL-BUDS Air``, ``KC87``, ``GM-X2``, ``PD100``.
_MODEL_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*")

#: Words that describe the question, not the product; they must not steer resolution.
_STOP_TOKENS = frozenset({"sku", "http", "https", "www", "com", "cny", "rmb"})


def model_tokens(text: str) -> tuple[str, ...]:
    """Return the ASCII model-code candidates in ``text``, lower-cased and unique.

    Pure-letter words ("Air", "Lite", "Pro") are kept only when they appear in the
    catalogue as part of a title, so "Air" alone cannot resolve a product.
    """
    tokens: list[str] = []
    for raw in _MODEL_TOKEN.findall(text or ""):
        token = raw.lower()
        if len(token) < 2 or token in _STOP_TOKENS or token in tokens:
            continue
        tokens.append(token)
    return tuple(tokens)


def resolve_catalog_item(
    text: str,
    items: Sequence[Mapping[str, Any]],
    *,
    categories: Sequence[str] = (),
) -> Mapping[str, Any] | None:
    """Return the single catalogue item ``text`` refers to, or ``None`` when ambiguous.

    Resolution order (each step must be unique, otherwise the next one runs):

    1. an explicit SKU / product id in the text;
    2. **all** model tokens of the text appear in the title (``SL-BUDS Air`` excludes
       ``SL-BUDS Lite``, which shares every other word);
    3. only one candidate carries a category word the text implies.

    Never guesses between two different products: a wrong id would turn an honest
    clarification into a confidently wrong price.
    """
    if not text or not items:
        return None
    lowered = text.lower()
    for item in items:
        for key in ("sku", "product_id", "variant_id"):
            value = item.get(key)
            if value and str(value).lower() in lowered:
                return item

    tokens = model_tokens(text)
    if tokens:
        matched = [
            item
            for item in items
            if all(token in str(item.get("title", "")).lower() for token in tokens)
        ]
        if len(matched) == 1:
            return matched[0]

    implied = category_terms(text)
    wanted = implied + tuple(c for c in categories if c not in implied)
    if wanted:
        on_topic = [
            item for item in items if any(term in str(item.get("title", "")) for term in wanted)
        ]
        if len(on_topic) == 1:
            return on_topic[0]
    return None


def best_overlap_item(
    text: str,
    items: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Return the item whose title shares the most bigrams with ``text``.

    A category-style comparison operand ("无线键盘" vs "机械键盘") names no single
    product, and the catalogue search ranks by query tokens — so both operands of
    one question can return the *same* top hit (the membrane keyboard tops both
    keyboard expansions), which would make a side compare a product with itself.
    Bigram overlap puts each operand's distinguishing word ("无线" / "机械") in
    charge; ties keep the incoming search order, and a text without CJK bigrams
    still returns the first item.
    """
    if not items:
        return None
    wanted = _bigrams(text)
    best = items[0]
    best_score = -1
    for item in items:
        score = len(wanted & _bigrams(str(item.get("title", ""))))
        if score > best_score:
            best, best_score = item, score
    return best


#: Wording that asks about *availability* rather than price/specs.
_STOCK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"还有货|有货吗|有没有货|有现货|现货|缺货|断货|无货|卖完了|还有吗|库存"),
)


def is_stock_question(text: str) -> bool:
    """Return True when the turn asks about availability (→ ``check_stock``)."""
    return any(pattern.search(text or "") for pattern in _STOCK_PATTERNS)


# -- comparison operands -------------------------------------------------------
#
# ``compare_products`` takes 2-4 product ids, but shoppers compare *names*
# ("声岚 SL-NC700 和 声岚 SL-NC500 有什么区别"). Stage 13 measured the cost: all 12
# comparison turns fell back to a clarification because only bare UUIDs were recognised.

#: Separators that join two operands. ``对比``/``比较`` are deliberately **not** separators:
#: they are also the verb ("A 和 B 对比一下"), and splitting on them would leave "一下".
_COMPARE_SPLIT = re.compile(r"\s*(?:和|与|跟|vs\.?)\s*", re.IGNORECASE)

#: Trailing question noise that must not become part of the product query.
_SIDE_NOISE = re.compile(
    r"(?:"
    r"有什么区别(?:呢|吗)?|有何区别|有什么区别和联系|的区别是什么|的区别|差异|不同点|"
    r"哪个好|哪款好|哪个更值得买|哪个更值得|更值得买|更值得|选哪个|怎么选|"
    r"对比一下|对比|比较一下|比较|怎么样|如何|"
    r"呢|吗|嘛|吧|的|？|\?|。|，|,|、|\s"
    r")+$"
)

#: Leading politeness that carries no product information.
_SIDE_LEAD = re.compile(r"^(?:请问|麻烦|帮我|我想|想|那|这两个|这两款|这个|这|和|与|跟)+")


def split_compare_sides(text: str) -> tuple[str, str] | None:
    """Split a comparison question into its two operands, or ``None``.

    Returns ``(left, right)`` with the question noise stripped from both sides. ``None``
    means "not a clean two-operand comparison" — the caller then keeps its clarification
    instead of comparing the wrong pair.
    """
    parts = [part for part in _COMPARE_SPLIT.split(text or "") if part.strip()]
    if len(parts) != 2:
        return None
    sides: list[str] = []
    for part in parts:
        side = _SIDE_NOISE.sub("", _SIDE_LEAD.sub("", part.strip())).strip()
        if len(side) < 2:
            return None
        sides.append(side)
    if sides[0] == sides[1]:
        return None
    return sides[0], sides[1]


__all__ = [
    "SYNONYMS",
    "best_overlap_item",
    "category_terms",
    "expand_query",
    "extract_budget_cents",
    "infer_return_reason",
    "is_stock_question",
    "match_line",
    "model_tokens",
    "resolve_catalog_item",
    "split_compare_sides",
]
