"""Rule-based intent routing for the ten ShopMate intents.

Routing is deterministic on purpose. It decides which tools are reachable, so a wrong
route is a permission bug, not a style issue. The router therefore:

* runs the risk table **first** — complaints, legal threats, account takeover and money
  demands become ``complaint_handoff`` before any other rule can win;
* scores the remaining intents with weighted patterns and resolves ties by specificity;
* requires ``>= INTENT_MIN_CONFIDENCE`` (default 0.70) before any tool is allowed; below
  it the route asks for clarification and exposes no tools;
* when the weighted table matched nothing — or only a generic pattern worth <= 2 — a
  knowledge-shaped turn (domain word / interrogative / bare question mark) is sent to the
  policy RAG path instead of smalltalk, so PolicyQAService's evidence gate gets to decide
  answer-vs-refuse. Turns carrying order/SKU ids, resolved referential follow-ups, risk
  overrides and instruction-override text are excluded; the switch
  ``knowledge_fallback_enabled`` turns it off for ablation;
* history only resolves a referential follow-up and may only escalate, never downgrade:
  it can add support to one intent for a zero-word follow-up such as "那它呢", but it can
  never pull a turn down to a safer or less specific route;
* a ``complaint_handoff`` route is always ``handoff_required``; routing to the handoff
  intent and the handoff flag can never disagree;
* marks a policy route cache-eligible only when it is low risk, confident, citation-based
  and free of order/SKU/product identifiers.

``return_request`` deliberately exposes only ``check_return_eligibility``: creating the
request is a stage-9 write tool that also needs an explicit server-side confirmation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.query_rewrite import (
    EntitySet,
    extract_entities,
    is_referential,
)
from shopmate_ecommerce_assistant.safety.risk import (
    RiskAssessment,
    RiskLevel,
    RiskSignals,
    assess_risk,
)

CLARIFICATION_TEXT = (
    "我还不能确定你想办理哪一类问题。可以补充一下是商品、政策、订单物流，还是退货售后吗？"
)


class Intent(StrEnum):
    """The twelve ShopMate intents (AGENTS.md §10.7 plus self-service purchase/refund)."""

    PRODUCT_DISCOVERY = "product_discovery"
    PRODUCT_COMPARE = "product_compare"
    PRODUCT_FACT = "product_fact"
    POLICY_FAQ = "policy_faq"
    ORDER_STATUS = "order_status"
    SHIPMENT = "shipment"
    RETURN_ELIGIBILITY = "return_eligibility"
    RETURN_REQUEST = "return_request"
    REFUND_STATUS = "refund_status"
    PURCHASE = "purchase"
    COMPLAINT_HANDOFF = "complaint_handoff"
    SMALLTALK_OR_UNKNOWN = "smalltalk_or_unknown"


class RoutePath(StrEnum):
    """The three execution paths plus the safe fallback."""

    STRUCTURED = "A_structured"
    KNOWLEDGE = "B_knowledge"
    DETERMINISTIC = "C_deterministic"
    SAFE_FALLBACK = "safe_fallback"


PATH_BY_INTENT: dict[Intent, RoutePath] = {
    Intent.PRODUCT_DISCOVERY: RoutePath.STRUCTURED,
    Intent.PRODUCT_COMPARE: RoutePath.STRUCTURED,
    Intent.PRODUCT_FACT: RoutePath.STRUCTURED,
    Intent.POLICY_FAQ: RoutePath.KNOWLEDGE,
    Intent.ORDER_STATUS: RoutePath.STRUCTURED,
    Intent.SHIPMENT: RoutePath.STRUCTURED,
    Intent.RETURN_ELIGIBILITY: RoutePath.DETERMINISTIC,
    Intent.RETURN_REQUEST: RoutePath.DETERMINISTIC,
    Intent.REFUND_STATUS: RoutePath.DETERMINISTIC,
    Intent.PURCHASE: RoutePath.STRUCTURED,
    Intent.COMPLAINT_HANDOFF: RoutePath.DETERMINISTIC,
    Intent.SMALLTALK_OR_UNKNOWN: RoutePath.SAFE_FALLBACK,
}

ALLOWED_TOOLS: dict[Intent, tuple[str, ...]] = {
    Intent.PRODUCT_DISCOVERY: ("search_products",),
    Intent.PRODUCT_COMPARE: ("search_products", "compare_products"),
    Intent.PRODUCT_FACT: (
        "search_products",
        "get_product_detail",
        "check_stock",
        "get_promotion",
    ),
    Intent.POLICY_FAQ: (),
    Intent.ORDER_STATUS: ("get_order_status",),
    Intent.SHIPMENT: ("get_order_status", "get_shipment"),
    Intent.RETURN_ELIGIBILITY: ("check_return_eligibility",),
    # ``create_return_request`` is stage 9 and requires a server-side confirmation grant.
    Intent.RETURN_REQUEST: ("check_return_eligibility",),
    # Refund progress is read from the caller's own rows; no tool is exposed.
    Intent.REFUND_STATUS: (),
    Intent.PURCHASE: ("search_products",),
    Intent.COMPLAINT_HANDOFF: (),
    Intent.SMALLTALK_OR_UNKNOWN: (),
}

#: Higher specificity first; used only to break exact ties.
PRIORITY: tuple[Intent, ...] = (
    Intent.COMPLAINT_HANDOFF,
    Intent.REFUND_STATUS,
    Intent.PURCHASE,
    Intent.RETURN_REQUEST,
    Intent.RETURN_ELIGIBILITY,
    Intent.SHIPMENT,
    Intent.ORDER_STATUS,
    Intent.PRODUCT_COMPARE,
    Intent.PRODUCT_FACT,
    Intent.POLICY_FAQ,
    Intent.PRODUCT_DISCOVERY,
    Intent.SMALLTALK_OR_UNKNOWN,
)

HANDOFF_INTENTS = frozenset(
    {
        Intent.COMPLAINT_HANDOFF,
        Intent.RETURN_REQUEST,
        Intent.RETURN_ELIGIBILITY,
        Intent.ORDER_STATUS,
        Intent.SHIPMENT,
        Intent.POLICY_FAQ,
    }
)


@dataclass(frozen=True, slots=True)
class IntentRule:
    """One weighted, named pattern."""

    label: str
    intent: Intent
    weight: int
    pattern: re.Pattern[str]


def _rule(label: str, intent: Intent, weight: int, pattern: str) -> IntentRule:
    return IntentRule(label, intent, weight, re.compile(pattern))


RULES: tuple[IntentRule, ...] = (
    # -- product discovery ------------------------------------------------
    _rule(
        "discover.recommend",
        Intent.PRODUCT_DISCOVERY,
        4,
        r"推荐|有什么好(?:的)?|挑(?:一个|一款)",
    ),
    _rule("discover.want", Intent.PRODUCT_DISCOVERY, 4, r"想买|想找|想选|想入手|打算买"),
    _rule("discover.budget", Intent.PRODUCT_DISCOVERY, 3, r"预算"),
    _rule("discover.fit", Intent.PRODUCT_DISCOVERY, 3, r"适合|用来|通勤|入门|性价比|平替"),
    _rule(
        "discover.cheaper",
        Intent.PRODUCT_DISCOVERY,
        2,
        r"便宜|实惠|省钱|便宜点|低一点",
    ),
    _rule("discover.any", Intent.PRODUCT_DISCOVERY, 2, r"有没有|有什么"),
    _rule(
        "discover.category",
        Intent.PRODUCT_DISCOVERY,
        2,
        r"降噪耳机|蓝牙耳机|机械键盘|无线鼠标|充电器|移动电源|智能手表|蓝牙音箱",
    ),
    # -- product compare --------------------------------------------------
    _rule("compare.difference", Intent.PRODUCT_COMPARE, 4, r"有什么区别|有何区别|区别|差异|不同点"),
    _rule("compare.compare", Intent.PRODUCT_COMPARE, 4, r"对比|比较|比一比|横向比"),
    _rule("compare.which", Intent.PRODUCT_COMPARE, 3, r"哪个好|哪款好|选哪个|更值得|怎么选"),
    # -- product fact -----------------------------------------------------
    _rule("fact.price", Intent.PRODUCT_FACT, 4, r"多少钱|什么价格|价格|售价|卖多少|几块钱"),
    _rule("fact.stock", Intent.PRODUCT_FACT, 4, r"库存|有货|还有货|缺货|现货|无货|断货"),
    _rule("fact.attribute", Intent.PRODUCT_FACT, 3, r"参数|规格|配置|尺寸|重量|续航|材质|颜色"),
    _rule(
        "fact.sku",
        Intent.PRODUCT_FACT,
        3,
        r"\bsku\b",
    ),
    _rule("fact.support", Intent.PRODUCT_FACT, 2, r"支持.{0,8}(?:吗|么)"),
    # -- policy FAQ -------------------------------------------------------
    _rule("policy.word", Intent.POLICY_FAQ, 3, r"政策|规定|规则|条款|须知"),
    _rule("policy.no_reason", Intent.POLICY_FAQ, 4, r"七天无理由|无理由退货"),
    _rule("policy.after_sale", Intent.POLICY_FAQ, 3, r"退换货|退货流程|退款流程|售后"),
    _rule("policy.freight", Intent.POLICY_FAQ, 3, r"运费|邮费|快递费"),
    _rule("policy.warranty", Intent.POLICY_FAQ, 4, r"保修|质保"),
    _rule("policy.invoice", Intent.POLICY_FAQ, 4, r"发票|开票"),
    _rule("policy.free_shipping", Intent.POLICY_FAQ, 3, r"包邮|免运费"),
    _rule(
        "policy.refund_time",
        Intent.POLICY_FAQ,
        4,
        r"多久(?:能|可以)?到账|到账时间|几天到账|多久能退",
    ),
    _rule("policy.calculation", Intent.POLICY_FAQ, 3, r"什么时候开始计算|怎么计算|如何计算"),
    _rule("policy.scope", Intent.POLICY_FAQ, 2, r"哪些商品|不适用|不支持"),
    _rule("policy.delivery", Intent.POLICY_FAQ, 2, r"配送|发货时效|时效"),
    _rule("policy.how", Intent.POLICY_FAQ, 2, r"能退(?:吗|么|嘛)|可以退(?:吗|么|嘛)|怎么退"),
    _rule("policy.promotion", Intent.POLICY_FAQ, 2, r"优惠券|满减|活动规则"),
    # -- order status -----------------------------------------------------
    _rule("order.status", Intent.ORDER_STATUS, 4, r"订单状态|订单进度|订单情况"),
    _rule("order.query", Intent.ORDER_STATUS, 3, r"我的订单|查订单|订单查询|订单号"),
    _rule("order.paid", Intent.ORDER_STATUS, 3, r"下单成功|支付成功"),
    # -- shipment ---------------------------------------------------------
    _rule("shipment.logistics", Intent.SHIPMENT, 4, r"物流|快递|运单|运输"),
    _rule("shipment.where", Intent.SHIPMENT, 4, r"到哪了|到哪里了|到哪"),
    _rule("shipment.shipped", Intent.SHIPMENT, 4, r"发货了吗|什么时候发货|发货时间|已发货"),
    _rule("shipment.progress", Intent.SHIPMENT, 3, r"派送|配送进度|签收|送达|包裹"),
    # -- return eligibility ----------------------------------------------
    _rule(
        "eligibility.can",
        Intent.RETURN_ELIGIBILITY,
        4,
        r"能退(?:吗|么|嘛)|可以退(?:吗|么|嘛)|能不能退|可以退货(?:吗|么|嘛)",
    ),
    _rule(
        "eligibility.condition",
        Intent.RETURN_ELIGIBILITY,
        4,
        r"符合.{0,6}退货|退货条件|退货资格|能申请退货|退货需要什么材料|退货材料",
    ),
    _rule(
        "eligibility.window",
        Intent.RETURN_ELIGIBILITY,
        3,
        r"还在.{0,6}(?:退货期|七天)|超过.{0,6}(?:七天|退货期)",
    ),
    _rule(
        "eligibility.order_item",
        Intent.RETURN_ELIGIBILITY,
        4,
        r"(?:这个|该|我的).{0,6}订单.{0,8}(?:能退|可以退|退货)",
    ),
    _rule("eligibility.reason", Intent.RETURN_ELIGIBILITY, 2, r"尺码不合适|不喜欢|不想要了"),
    # -- return request ---------------------------------------------------
    _rule(
        "request.apply",
        Intent.RETURN_REQUEST,
        4,
        r"我要退货|我想退货|要退货|申请退货|提交退货|发起退货|办理退货|帮我退货|退货申请",
    ),
    _rule("request.submit", Intent.RETURN_REQUEST, 3, r"申请退款|退掉这个|直接退|我要退掉"),
    # -- refund progress / purchase ---------------------------------------
    _rule(
        "refund.progress",
        Intent.REFUND_STATUS,
        4,
        r"退款进度|退款到哪|退款状态|退款到账|我的退款|已退款|退款申请(?:记录|状态|进度)?",
    ),
    _rule(
        "refund.apply",
        Intent.REFUND_STATUS,
        4,
        r"(?:我要|我想|申请|想申请|要申请|帮我)\s*(?:退款|退钱)|退钱",
    ),
    _rule(
        "purchase.how",
        Intent.PURCHASE,
        4,
        r"怎么(?:买|下单)|在哪(?:买|下单)|如何(?:买|下单)|下单流程|购买流程|怎么购买",
    ),
    _rule("purchase.checkout", Intent.PURCHASE, 3, r"下单|结算|去支付|加入购物车|立即购买"),
    # -- complaint / handoff ---------------------------------------------
    _rule("handoff.complaint", Intent.COMPLAINT_HANDOFF, 4, r"投诉|举报|维权|差评|曝光你们"),
    _rule("handoff.human", Intent.COMPLAINT_HANDOFF, 3, r"转人工|找人工|要人工|真人客服|客服主管"),
    _rule("handoff.emotion", Intent.COMPLAINT_HANDOFF, 2, r"太差|垃圾|骗子|很愤怒"),
    # -- smalltalk --------------------------------------------------------
    _rule("smalltalk.greet", Intent.SMALLTALK_OR_UNKNOWN, 3, r"你好|您好|在吗|嗨|hello|hi\b"),
    _rule("smalltalk.thanks", Intent.SMALLTALK_OR_UNKNOWN, 3, r"谢谢|感谢|辛苦了"),
    _rule("smalltalk.bye", Intent.SMALLTALK_OR_UNKNOWN, 3, r"再见|拜拜"),
    _rule("smalltalk.identity", Intent.SMALLTALK_OR_UNKNOWN, 2, r"你是谁|你能做什么|怎么使用你"),
    _rule("smalltalk.offtopic", Intent.SMALLTALK_OR_UNKNOWN, 1, r"天气|笑话|唱歌"),
)

#: Risk codes that force ``complaint_handoff`` regardless of the scored intent.
OVERRIDE_CODES = frozenset(
    {
        "USER_REQUESTS_HUMAN",
        "COMPLAINT",
        "LEGAL_OR_REGULATORY",
        "PERSONAL_SAFETY",
        "PRIVACY_OR_ACCOUNT_TAKEOVER",
        "MONEY_DECISION_REQUIRED",
    }
)

# -- knowledge fallback (stage 18) ---------------------------------------------
#
# The weighted table only recognises phrasings somebody wrote down. Stage 13 measured the
# cost: 20 of 36 policy questions were routed elsewhere, 12 of them to smalltalk with a
# zero score, and none of the seven ``no_answer`` cases ever reached the evidence gate, so
# strict refusal was structurally 0/7. The tables below are the *topic* vocabulary, kept
# apart from ``RULES`` on purpose: they decide "is this a knowledge question?", never "which
# tool to call". Whether the corpus actually supports an answer stays with
# PolicyQAService and ``policy_min_evidence_similarity`` — the fallback must not answer.
KNOWLEDGE_DOMAIN_TERMS: tuple[str, ...] = (
    "政策",
    "规定",
    "规则",
    "条款",
    "须知",
    "售后",
    "退换",
    "退货",
    "退款",
    "换货",
    "换新",
    "保修",
    "质保",
    "维修",
    "发票",
    "开票",
    "运费",
    "邮费",
    "快递费",
    "包邮",
    "免运费",
    "价保",
    "保价",
    "补差价",
    "降价",
    "优惠券",
    "满减",
    "促销",
    "积分",
    "会员",
    "分期",
    "手续费",
    "到账",
    "时效",
    "发货",
    "配送",
    "签收",
    "破损",
    "丢件",
    "以旧换新",
    "定制",
    "刻字",
    "拆封",
    "试用",
    "试戴",
    "门店",
    "预约",
    "企业采购",
    "框架协议",
    "支付方式",
    "付款",
    "货到付款",
    "附加运费",
    "退货期",
)

INTERROGATIVE_MARKERS: tuple[str, ...] = (
    "吗",
    "呢",
    "嘛",
    "怎么",
    "如何",
    "能不能",
    "可不可以",
    "是否",
    "多久",
    "多少钱",
    "几天",
    "几点",
    "哪些",
    "什么",
    "多少",
)

#: Condition (c): a question mark *plus* no explicit search/order action. The action words
#: exist so that "帮我查订单 DEMO-1001 的进度？" stays on the structured path.
SEARCH_ACTION_TERMS: tuple[str, ...] = (
    "推荐",
    "想买",
    "买",
    "下单",
    "购物车",
    "结算",
    "搜索",
    "帮我查",
    "查订单",
    "我的订单",
    "订单号",
    "物流单号",
    "运单号",
    "到哪了",
    "发货了吗",
    "还有货",
    "价格",
    "多少钱",
)

#: Texts that try to override instructions are handled as a safety matter, not as a
#: knowledge question; letting the fallback claim them would hide the injection case.
INSTRUCTION_OVERRIDE_MARKERS: tuple[str, ...] = (
    "忽略",
    "系统指令",
    "系统提示",
    "system prompt",
)

#: Fallback scores reuse the existing ``_confidence`` formula instead of a new constant:
#: 3 -> 0.79 (domain word) and 2 -> 0.71 (interrogative / question mark), both above the
#: default 0.70 gate. That is routing confidence ("this is a knowledge question"), not
#: answer confidence; the evidence gate still decides whether an answer is allowed.
KNOWLEDGE_FALLBACK_DOMAIN_SCORE = 3
KNOWLEDGE_FALLBACK_WEAK_SCORE = 2

#: A business match at or below this score carries no specific signal: it comes from
#: generic patterns ("支持…吗" = 2, "有没有" = 2) that say nothing about the tool needed.
KNOWLEDGE_FALLBACK_MAX_WEAK_SCORE = 2


def knowledge_fallback_reason(text: str) -> str | None:
    """Return which knowledge-fallback condition ``text`` satisfies, or ``None``.

    Order matters: a domain word is the strongest evidence, then an interrogative of
    reasonable length, then a bare question mark without a search/order action.
    """
    normalized = " ".join((text or "").split())
    if not normalized:
        return None
    if any(marker in normalized for marker in INSTRUCTION_OVERRIDE_MARKERS):
        return None
    if any(term in normalized for term in KNOWLEDGE_DOMAIN_TERMS):
        return "domain"
    if any(marker in normalized for marker in INTERROGATIVE_MARKERS) and len(normalized) >= 8:
        return "interrogative"
    if ("？" in normalized or "?" in normalized) and not any(
        term in normalized for term in SEARCH_ACTION_TERMS
    ):
        return "question_mark"
    return None


def _knowledge_fallback(
    *,
    text: str,
    best_score: int,
    entities: EntitySet,
    history_used: bool,
    text_risk: RiskAssessment,
    settings: Settings,
) -> tuple[Intent, int, str] | None:
    """Decide whether a would-be ``smalltalk_or_unknown`` turn belongs to the RAG path.

    Returns ``(intent, score, label)`` or ``None``. Guard rails, in order:

    * the switch is off (ablation);
    * the turn carries an order number / SKU / product id — structured facts must come from
      structured sources, so those never go to the document RAG path;
    * history already resolved a referential follow-up (never downgrade a resolved turn);
    * a risk override applies (complaint / legal / money demands keep their own route).
    """
    if not settings.knowledge_fallback_enabled:
        return None
    if history_used or entities.has_realtime_id():
        return None
    if OVERRIDE_CODES & set(text_risk.codes):
        return None
    reason = knowledge_fallback_reason(text)
    if reason is None:
        return None
    if best_score <= 0:
        score = (
            KNOWLEDGE_FALLBACK_DOMAIN_SCORE if reason == "domain" else KNOWLEDGE_FALLBACK_WEAK_SCORE
        )
        return Intent.POLICY_FAQ, score, f"knowledge_fallback:{reason}"
    # A weak-only match ("支持…吗", "有没有…") is not evidence for *either* side: it is a
    # generic question shape. Only a domain word may promote such a turn, so
    # "充电器支持快充吗？" stays a product fact question.
    if (
        settings.knowledge_fallback_weak_intent_enabled
        and reason == "domain"
        and best_score <= KNOWLEDGE_FALLBACK_MAX_WEAK_SCORE
    ):
        return Intent.POLICY_FAQ, KNOWLEDGE_FALLBACK_DOMAIN_SCORE, "knowledge_fallback:domain:weak"
    return None



@dataclass(frozen=True, slots=True)
class IntentRoute:
    """The routing decision with everything the chat path needs to proceed."""

    intent: Intent
    confidence: float
    path: RoutePath
    allowed_tools: tuple[str, ...]
    risk: RiskAssessment
    entities: EntitySet
    reasons: tuple[str, ...] = ()
    requires_clarification: bool = False
    handoff_required: bool = False
    cache_eligible: bool = False
    history_used: bool = False
    clarification_text: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the SSE ``meta``/audit representation."""
        return {
            "route": self.intent.value,
            "confidence": self.confidence,
            "path": self.path.value,
            "allowed_tools": list(self.allowed_tools),
            "risk_level": self.risk.level.value,
            "risk_codes": list(self.risk.codes),
            "primary_reason_code": self.risk.primary_reason_code,
            "requires_clarification": self.requires_clarification,
            "handoff_required": self.handoff_required,
            "cache_eligible": self.cache_eligible,
            "history_used": self.history_used,
            "reasons": list(self.reasons),
        }


def _score(text: str) -> tuple[dict[Intent, int], dict[Intent, list[str]]]:
    scores: dict[Intent, int] = {intent: 0 for intent in Intent}
    reasons: dict[Intent, list[str]] = {intent: [] for intent in Intent}
    for rule in RULES:
        if rule.pattern.search(text):
            scores[rule.intent] += rule.weight
            reasons[rule.intent].append(rule.label)
    return scores, reasons


def _entity_boost(intent: Intent, entities: EntitySet) -> float:
    if intent in {Intent.ORDER_STATUS, Intent.SHIPMENT} and entities.order_nos:
        return 0.05
    if intent in {Intent.RETURN_ELIGIBILITY, Intent.RETURN_REQUEST} and (
        entities.order_nos or entities.skus
    ):
        return 0.05
    if intent in {Intent.PRODUCT_FACT, Intent.PRODUCT_COMPARE} and (
        entities.product_ids or entities.skus
    ):
        return 0.05
    if intent is Intent.POLICY_FAQ and entities.regions:
        return 0.03
    if intent is Intent.PRODUCT_DISCOVERY and entities.amounts_cents:
        return 0.03
    return 0.0


def _confidence(score: int, boost: float) -> float:
    if score <= 0:
        return 0.30
    return min(0.97, round(0.55 + 0.08 * score + boost, 3))


def _pick(scores: dict[Intent, int], reasons: dict[Intent, list[str]]) -> tuple[Intent, int]:
    best_score = max(scores.values())
    if best_score <= 0:
        return Intent.SMALLTALK_OR_UNKNOWN, 0
    for intent in PRIORITY:
        if scores[intent] == best_score:
            return intent, best_score
    return Intent.SMALLTALK_OR_UNKNOWN, 0


def _history_entities(history: Sequence[str]) -> EntitySet:
    merged = EntitySet()
    for turn in history[-4:]:
        entities = extract_entities(turn)
        merged = merged.merged(
            EntitySet(
                order_nos=entities.order_nos,
                product_ids=entities.product_ids,
                skus=entities.skus,
            )
        )
    return merged


def _history_hint(
    history: Sequence[str], *, settings: Settings, threshold: float
) -> tuple[Intent | None, float]:
    """Return the most recent confident intent for a referential follow-up."""
    for turn in reversed(history[-3:]):
        if not turn.strip():
            continue
        sub = route_intent(turn, history=(), settings=settings, _depth=1)
        if sub.confidence >= threshold and sub.intent is not Intent.SMALLTALK_OR_UNKNOWN:
            return sub.intent, 2.0
    return None, 0.0


def route_intent(
    text: str,
    *,
    history: Sequence[str] = (),
    settings: Settings | None = None,
    _depth: int = 0,
) -> IntentRoute:
    """Route one user turn to exactly one of the ten intents.

    Args:
        text: input-guarded user text.
        history: recent user turns (oldest first), used only for references.
        settings: supplies ``intent_min_confidence``.
        _depth: internal recursion guard for the history hint.
    """
    resolved = settings or Settings(_env_file=None)  # type: ignore[call-arg]
    threshold = resolved.intent_min_confidence
    cleaned = " ".join((text or "").split())
    entities = extract_entities(cleaned)

    scores, reasons = _score(cleaned)
    history_used = False
    if is_referential(cleaned) and history and _depth == 0:
        hint, bonus = _history_hint(history, settings=resolved, threshold=threshold)
        if hint is not None:
            scores[hint] += int(bonus)
            reasons[hint].append(f"history_intent:{hint.value}")
            history_used = True
            history_ids = _history_entities(history)
            entities = entities.merged(
                EntitySet(
                    order_nos=history_ids.order_nos,
                    product_ids=history_ids.product_ids,
                    skus=history_ids.skus,
                )
            )

    intent, score = _pick(scores, reasons)
    text_risk = assess_risk(cleaned)
    fallback = _knowledge_fallback(
        text=cleaned,
        best_score=max(scores.values()),
        entities=entities,
        history_used=history_used,
        text_risk=text_risk,
        settings=resolved,
    )
    knowledge_fallback_used = fallback is not None
    if fallback is not None:
        intent, score, fallback_label = fallback
        reasons[intent].append(fallback_label)

    boost = _entity_boost(intent, entities)
    confidence = _confidence(score, boost)
    if boost:
        reasons[intent].append("entity_support")

    if OVERRIDE_CODES & set(text_risk.codes):
        intent = Intent.COMPLAINT_HANDOFF
        confidence = max(confidence, 0.90)
        reasons[intent].append("risk_override")

    amount = max(entities.amounts_cents, default=None)
    risk = assess_risk(
        cleaned,
        signals=RiskSignals(
            amount_cents=amount,
            intent=intent.value,
            confidence=confidence,
            rights_affected=intent in HANDOFF_INTENTS,
        ),
        low_confidence_threshold=threshold,
    )

    requires_clarification = confidence < threshold and not risk.handoff_required
    if risk.handoff_required and intent is not Intent.COMPLAINT_HANDOFF:
        # Low-confidence-but-rights-affecting turns hand off without relabelling the topic.
        reasons[intent].append("handoff_required")
    if requires_clarification:
        path = RoutePath.SAFE_FALLBACK
        allowed: tuple[str, ...] = ()
    else:
        path = PATH_BY_INTENT[intent]
        allowed = ALLOWED_TOOLS[intent] if not risk.handoff_required else ()

    cache_eligible = (
        intent is Intent.POLICY_FAQ
        and not risk.handoff_required
        and not requires_clarification
        and risk.level is RiskLevel.LOW
        and not entities.has_realtime_id()
        # A refusal that only exists because a question *shape* matched is not worth
        # caching: the same shape can carry an answerable question next time.
        and not knowledge_fallback_used
    )

    return IntentRoute(
        intent=intent,
        confidence=confidence,
        path=path,
        allowed_tools=allowed,
        risk=risk,
        entities=entities,
        reasons=tuple(dict.fromkeys(reasons[intent])),
        requires_clarification=requires_clarification,
        # A complaint route that is not marked for handoff would neither escalate nor
        # expose a tool: the user would be stuck. The two must never disagree.
        handoff_required=risk.handoff_required or intent is Intent.COMPLAINT_HANDOFF,
        cache_eligible=cache_eligible,
        history_used=history_used,
        clarification_text=CLARIFICATION_TEXT if requires_clarification else None,
    )


__all__ = [
    "ALLOWED_TOOLS",
    "CLARIFICATION_TEXT",
    "INTERROGATIVE_MARKERS",
    "Intent",
    "IntentRoute",
    "IntentRule",
    "KNOWLEDGE_DOMAIN_TERMS",
    "PATH_BY_INTENT",
    "PRIORITY",
    "RULES",
    "RoutePath",
    "SEARCH_ACTION_TERMS",
    "knowledge_fallback_reason",
    "route_intent",
]
