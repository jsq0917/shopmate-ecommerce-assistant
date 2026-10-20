"""History-aware, deterministic query rewriting.

Why deterministic: a rewritten query decides *what gets retrieved*, so letting a model
rewrite it would make recall non-reproducible and give an injected document a path into
the retrieval query. This module therefore uses only rules, entity patterns and a bounded
synonym table.

Hard constraints (AGENTS.md §10.7, §10.4):

* a short, complete question is **not** rewritten at all;
* history may only fill in pronouns and identifiers, never change the intent;
* order numbers, product ids, SKUs, amounts, dates and regions survive every strategy;
* keyword expansion is bounded, and there are never more than three sub-queries;
* sub-queries are **audit only**. ``QueryPlan.subqueries`` records how a multi-clause
  question could be split, but this module does not fan out into several retrievals: the
  chat path embeds ``primary_query`` only. Adding multi-query recall is a separate,
  evaluated change (it changes latency and the hybrid top-k contract), so it must not be
  inferred from this field;
* **no embedding happens here.** The rewritten text is embedded later by the same
  ``DocumentRetriever``/BGE-M3 singleton used in stage 7 — there is no second encoder,
  no BM25 and no separate sparse implementation in this path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shopmate_ecommerce_assistant.core.config import Settings

WHITESPACE = re.compile(r"\s+")
UUID_PATTERN = re.compile(
    r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9a-fA-F])"
)
ORDER_NO_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:DEMO|ORD|SO|SHP)[-_]?\d{3,8}(?![0-9])", re.I)
ORDER_CONTEXT_PATTERN = re.compile(r"订单(?:号|编号)?\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9-]{3,})")
SKU_PATTERN = re.compile(r"(?<![A-Za-z0-9-])[A-Za-z]{2,7}(?:-[A-Za-z0-9]{2,}){2,}(?![A-Za-z0-9-])")
#: One numeric literal with optional thousand separators. Grouped digits must be parsed as a
#: single value: before this, "6,000 元" matched only "000 元" and became 0 cents, which
#: silently disabled the ``HIGH_VALUE_ORDER`` risk rule for a ¥6,000 return.
_NUMBER = r"(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d{1,2})?"
AMOUNT_PATTERN = re.compile(
    rf"(?:￥|¥|RMB|CNY)?\s*({_NUMBER})\s*(?:元|块钱|块|RMB|CNY|人民币)", re.I
)
BUDGET_PATTERN = re.compile(rf"预算\s*(?:不超过|最多|在)?\s*({_NUMBER})")
DATE_PATTERN = re.compile(
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?"
    r"|\d{1,2}\s*月\s*\d{1,2}\s*日"
)
RELATIVE_DATE_PATTERN = re.compile(r"今天|昨天|前天|上周|本周|这周|上个月|本月|去年")

#: Longest first so "中国香港" is not also counted as "香港".
REGION_TERMS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("中国大陆", "CN"),
            ("中国香港", "HK"),
            ("中国澳门", "MO"),
            ("中国台湾", "TW"),
            ("大陆", "CN"),
            ("国内", "CN"),
            ("香港", "HK"),
            ("澳门", "MO"),
            ("台湾", "TW"),
            ("新加坡", "SG"),
            ("马来西亚", "MY"),
            ("泰国", "TH"),
            ("日本", "JP"),
            ("韩国", "KR"),
            ("美国", "US"),
            ("加拿大", "CA"),
            ("澳大利亚", "AU"),
            ("英国", "GB"),
            ("欧洲", "EU"),
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

ANCHOR_PATTERN = re.compile(
    r"退货|退款|换货|运费|保修|质保|发票|配送|包邮|物流|快递|订单|发货|签收|"
    r"优惠|活动|政策|规则|条款|耳机|键盘|鼠标|充电|手表|音箱|商品|库存|价格|多少钱"
)
REFERENTIAL_PATTERN = re.compile(
    r"^(?:那|这|它|他|她|他们|她们|上面|前面|刚才|刚刚|还有|再)|"
    r"这个|那个|这两|那两|这款|那款|它家|同款|另一个|上述"
)
PRONOUN_PATTERN = re.compile(
    r"^(?:那|这)(?![个款两些种里边时])(?=[\u4e00-\u9fffA-Za-z])|"
    r"这两款|那两款|这两个|那两个|这款|那款|这个|那个|它们|它|他们|她们|上述|前面说的"
)
TRAILING_PARTICLE = re.compile(r"[呢呀啊吧嘛]+$")
FILLER_PREFIXES: tuple[str, ...] = (
    "请问一下",
    "请问",
    "你好",
    "您好",
    "麻烦你",
    "麻烦",
    "想问一下",
    "我想问一下",
    "我想问",
    "我想知道",
    "帮我看看",
    "帮我查一下",
    "帮我查查",
    "那个",
    "嗯",
)
CLAUSE_SPLIT = re.compile(r"[？?；;。\n，,]+|(?:另外|还有|以及|顺便问一下)[，,]?")

#: Small, auditable synonym table. Each entry is (trigger, expansions).
KEYWORD_EXPANSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("降噪", ("主动降噪", "ANC")),
    ("通勤", ("地铁", "公交")),
    ("退货", ("无理由退货", "退换")),
    ("退款", ("退款到账",)),
    ("运费", ("寄回运费", "快递费")),
    ("保修", ("质保", "保修期")),
    ("发票", ("开票", "电子发票")),
    ("物流", ("快递", "运单")),
    ("发货", ("出库", "配送")),
    ("签收", ("收货", "送达")),
    ("优惠券", ("代金券", "满减")),
    ("包邮", ("免运费",)),
    ("库存", ("现货", "有货")),
)

SHORT_QUERY_CHARS = 24
MAX_TOPIC_CHARS = 60


@dataclass(frozen=True, slots=True)
class EntitySet:
    """Entities that must survive rewriting."""

    order_nos: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    skus: tuple[str, ...] = ()
    amounts_cents: tuple[int, ...] = ()
    dates: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()

    def any(self) -> bool:
        """Return True when at least one entity was found."""
        return bool(
            self.order_nos
            or self.product_ids
            or self.skus
            or self.amounts_cents
            or self.dates
            or self.regions
        )

    def has_realtime_id(self) -> bool:
        """Return True for identifiers that make a result user-specific/real-time."""
        return bool(self.order_nos or self.product_ids or self.skus)

    def contains(self, other: EntitySet) -> bool:
        """Return True when every entity of ``other`` is present in ``self``."""
        return (
            set(other.order_nos) <= set(self.order_nos)
            and set(other.product_ids) <= set(self.product_ids)
            and set(other.skus) <= set(self.skus)
            and set(other.amounts_cents) <= set(self.amounts_cents)
            and set(other.dates) <= set(self.dates)
            and set(other.regions) <= set(self.regions)
        )

    def merged(self, other: EntitySet) -> EntitySet:
        """Union two entity sets, preserving order and removing duplicates."""

        def _merge(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
            return tuple(dict.fromkeys((*left, *right)))

        return EntitySet(
            order_nos=_merge(self.order_nos, other.order_nos),
            product_ids=_merge(self.product_ids, other.product_ids),
            skus=_merge(self.skus, other.skus),
            amounts_cents=tuple(dict.fromkeys((*self.amounts_cents, *other.amounts_cents))),
            dates=_merge(self.dates, other.dates),
            regions=_merge(self.regions, other.regions),
        )

    def tokens(self) -> tuple[str, ...]:
        """Render every entity back to text (used to repair a dropped entity)."""
        tokens: list[str] = [
            *self.order_nos,
            *self.product_ids,
            *self.skus,
            *self.dates,
            *self.regions,
            *(f"{cents / 100:.2f} 元" for cents in self.amounts_cents),
        ]
        return tuple(dict.fromkeys(tokens))

    def as_dict(self) -> dict[str, list[object]]:
        """Return a JSON-serialisable audit representation."""
        return {
            "order_nos": list(self.order_nos),
            "product_ids": list(self.product_ids),
            "skus": list(self.skus),
            "amounts_cents": list(self.amounts_cents),
            "dates": list(self.dates),
            "regions": list(self.regions),
        }


def _to_cents(raw: str) -> int | None:
    # ``Decimal`` rejects "1,299"; the separators are presentation, not value.
    normalized = raw.replace(",", "").replace("，", "").strip()
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    cents = int(value * 100)
    return cents if cents >= 0 else None


def extract_entities(text: str) -> EntitySet:
    """Extract the identifiers and values that rewriting must preserve."""
    if not text:
        return EntitySet()
    order_nos: list[str] = [match.group(0) for match in ORDER_NO_PATTERN.finditer(text)]
    order_nos.extend(
        match.group(1) for match in ORDER_CONTEXT_PATTERN.finditer(text) if len(match.group(1)) >= 4
    )
    product_ids = [match.group(0) for match in UUID_PATTERN.finditer(text)]
    skus = [
        match.group(0) for match in SKU_PATTERN.finditer(text) if match.group(0) not in product_ids
    ]
    amounts: list[int] = []
    for pattern in (AMOUNT_PATTERN, BUDGET_PATTERN):
        for match in pattern.finditer(text):
            cents = _to_cents(match.group(1))
            if cents is not None:
                amounts.append(cents)
    dates = [match.group(0).strip() for match in DATE_PATTERN.finditer(text)]
    dates.extend(match.group(0) for match in RELATIVE_DATE_PATTERN.finditer(text))
    regions: list[str] = []
    for term, code in REGION_TERMS:
        if term in text and code not in regions:
            regions.append(code)
    return EntitySet(
        order_nos=tuple(dict.fromkeys(order_nos)),
        product_ids=tuple(dict.fromkeys(product_ids)),
        skus=tuple(dict.fromkeys(skus)),
        amounts_cents=tuple(dict.fromkeys(amounts)),
        dates=tuple(dict.fromkeys(dates)),
        regions=tuple(regions),
    )


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """The rewriting decision for one user turn, with an audit trail."""

    original: str
    core_query: str
    primary_query: str
    expanded_query: str
    subqueries: tuple[str, ...]
    strategies: tuple[str, ...]
    entities_before: EntitySet
    entities_after: EntitySet
    keywords_added: tuple[str, ...] = ()
    embedding_performed: bool = False

    @property
    def changed(self) -> bool:
        """Return True when the primary query differs from the user's wording."""
        return self.primary_query != self.original

    @property
    def entities_preserved(self) -> bool:
        """Return True when every original entity survives rewriting."""
        return self.entities_after.contains(self.entities_before)

    def audit(self) -> dict[str, object]:
        """Return the record required by AGENTS.md §10.7 (original, result, strategy)."""
        return {
            "original": self.original,
            "core_query": self.core_query,
            "primary_query": self.primary_query,
            "expanded_query": self.expanded_query,
            "strategies": list(self.strategies),
            "changed": self.changed,
            "keywords_added": list(self.keywords_added),
            "subquery_count": len(self.subqueries),
            "subqueries": list(self.subqueries),
            "entities_before": self.entities_before.as_dict(),
            "entities_after": self.entities_after.as_dict(),
            "entities_preserved": self.entities_preserved,
            "embedding_performed": self.embedding_performed,
        }


def _compact(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def _is_referential(text: str) -> bool:
    return bool(REFERENTIAL_PATTERN.search(text))


def _is_complete_short(text: str, entities: EntitySet) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) > SHORT_QUERY_CHARS:
        return False
    if _is_referential(text):
        return False
    return bool(entities.any() or ANCHOR_PATTERN.search(text))


def _strip_filler(text: str) -> str:
    result = text
    changed = True
    while changed:
        changed = False
        for prefix in FILLER_PREFIXES:
            if result.startswith(prefix):
                result = result[len(prefix) :].lstrip("，,。.？? ")
                changed = True
                break
    return result.strip()


def _recent_topic(history: tuple[str, ...]) -> str:
    """Return the most recent topic-bearing user turn, or an empty string."""
    for turn in reversed(history):
        candidate = _strip_filler(_compact(turn))
        if not candidate or _is_referential(candidate):
            continue
        if ANCHOR_PATTERN.search(candidate) or extract_entities(candidate).any():
            return candidate[:MAX_TOPIC_CHARS]
    return ""


def _carryover_ids(
    current: EntitySet, history_entities: EntitySet, *, referential: bool
) -> tuple[EntitySet, tuple[str, ...]]:
    """Carry identifiers only, only for a referential follow-up, at most one per kind."""
    if not referential:
        return EntitySet(), ()
    carried: list[str] = []
    order_nos: tuple[str, ...] = ()
    skus: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    if not current.order_nos and history_entities.order_nos:
        order_nos = history_entities.order_nos[-1:]
        carried.extend(order_nos)
    if not current.skus and history_entities.skus:
        skus = history_entities.skus[-1:]
        carried.extend(skus)
    if not current.product_ids and history_entities.product_ids:
        product_ids = history_entities.product_ids[-1:]
        carried.extend(product_ids)
    return (
        EntitySet(order_nos=order_nos, product_ids=product_ids, skus=skus),
        tuple(carried),
    )


def _expand_keywords(text: str, limit: int) -> tuple[str, ...]:
    if limit <= 0:
        return ()
    lowered = text.lower()
    added: list[str] = []
    for trigger, expansions in KEYWORD_EXPANSIONS:
        if trigger not in text:
            continue
        for expansion in expansions:
            if expansion.lower() in lowered or expansion in added:
                continue
            added.append(expansion)
            if len(added) >= limit:
                return tuple(added)
    return tuple(added)


def _split_clauses(text: str) -> tuple[str, ...]:
    clauses = [_compact(clause) for clause in CLAUSE_SPLIT.split(text)]
    return tuple(clause for clause in clauses if len(re.sub(r"\s+", "", clause)) >= 6)


def _repair_entities(query: str, entities: EntitySet) -> str:
    """Append any entity that a strategy accidentally dropped (defensive invariant)."""
    present = extract_entities(query)
    missing = [
        token
        for token in entities.tokens()
        if token and token not in query and not present.contains(extract_entities(token))
    ]
    if not missing:
        return query
    return f"{query} {' '.join(missing)}".strip()


def is_referential(text: str) -> bool:
    """Return True when the text depends on the previous turn (这对/那款/它...)."""
    return _is_referential(text)


def plan_query(
    question: str,
    *,
    history: tuple[str, ...] = (),
    settings: Settings | None = None,
    intent: str | None = None,
) -> QueryPlan:
    """Decide whether and how to rewrite ``question``.

    Args:
        question: current user text (already input-guarded).
        history: recent user turns, oldest first; only used to resolve references.
        settings: provides the keyword/sub-query caps.
        intent: router intent; ``smalltalk_or_unknown`` disables expansion.

    Returns:
        A :class:`QueryPlan`; ``primary_query`` is what retrieval should embed.

    ``subqueries`` is a bounded, audited list of alternative phrasings for logging and
    evaluation. It is **not** executed here: this function performs no retrieval fan-out,
    so callers must not assume one embedding per sub-query.
    """
    resolved = settings or Settings(_env_file=None)  # type: ignore[call-arg]
    original = _compact(question)
    entities = extract_entities(original)
    strategies: list[str] = []
    core = original
    stripped = original

    if not original:
        return QueryPlan(
            original="",
            core_query="",
            primary_query="",
            expanded_query="",
            subqueries=(),
            strategies=("empty",),
            entities_before=EntitySet(),
            entities_after=EntitySet(),
        )

    if _is_complete_short(original, entities):
        return QueryPlan(
            original=original,
            core_query=original,
            primary_query=original,
            expanded_query=original,
            subqueries=(original,),
            strategies=("none",),
            entities_before=entities,
            entities_after=entities,
        )

    if _is_referential(original):
        topic = _recent_topic(history)
        stripped = _compact(TRAILING_PARTICLE.sub("", PRONOUN_PATTERN.sub("", original)))
        needs_topic = not ANCHOR_PATTERN.search(stripped) and not extract_entities(stripped).any()
        if topic and needs_topic:
            core = _compact(f"{topic} {stripped}")
            strategies.append("history_topic")
        elif stripped and stripped != original:
            core = stripped
            strategies.append("pronoun_stripped")
        history_entities = extract_entities(" ".join(history[-4:]))
        carry, carried_tokens = _carryover_ids(entities, history_entities, referential=True)
        if carried_tokens:
            core = _compact(f"{core} {' '.join(carried_tokens)}")
            strategies.append("entity_carryover")
    else:
        stripped = _strip_filler(original)
        if stripped and stripped != original:
            core = stripped
            strategies.append("strip_filler")

    keywords = ()
    complete_after_pronoun = _is_referential(original) and _is_complete_short(stripped, entities)
    if intent != "smalltalk_or_unknown" and not complete_after_pronoun:
        keywords = _expand_keywords(core, resolved.query_rewrite_max_keywords)
    expanded = _compact(f"{core} {' '.join(keywords)}") if keywords else core
    if keywords:
        strategies.append("keyword_expansion")

    primary = expanded
    primary = _repair_entities(primary, entities)
    if primary != expanded:
        strategies.append("entity_repair")

    candidates: list[str] = []
    clauses = _split_clauses(core)
    if 2 <= len(clauses) <= resolved.query_rewrite_max_subqueries:
        candidates.extend(clauses)
        strategies.append("subquery_split")
    candidates.append(core)
    if expanded != core:
        candidates.append(expanded)
    if primary != expanded:
        candidates.append(primary)
    subqueries = tuple(dict.fromkeys(item for item in candidates if item.strip()))[
        : resolved.query_rewrite_max_subqueries
    ]

    after = extract_entities(primary)
    return QueryPlan(
        original=original,
        core_query=core,
        primary_query=primary,
        expanded_query=expanded,
        subqueries=subqueries or (primary,),
        strategies=tuple(dict.fromkeys(strategies)) or ("none",),
        entities_before=entities,
        entities_after=after,
        keywords_added=keywords,
    )


__all__ = [
    "KEYWORD_EXPANSIONS",
    "EntitySet",
    "QueryPlan",
    "extract_entities",
    "is_referential",
    "plan_query",
]
