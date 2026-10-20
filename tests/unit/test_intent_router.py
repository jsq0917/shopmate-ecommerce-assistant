"""Intent router: ten intents, risk precedence, confidence gate and history.

Every intent has at least three cases (AGENTS.md stage-8 acceptance). The cases use the
same phrasing as ``data/eval/eval_questions.jsonl`` where possible so a routing change is
visible against the evaluation set.
"""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.agents.router import (
    ALLOWED_TOOLS,
    Intent,
    RoutePath,
    route_intent,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.safety.risk import RiskLevel

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # product_discovery
        ("预算 300 元以内，适合通勤的降噪耳机", Intent.PRODUCT_DISCOVERY),
        ("想买机械键盘，有什么推荐？", Intent.PRODUCT_DISCOVERY),
        ("有没有适合学生用的无线鼠标", Intent.PRODUCT_DISCOVERY),
        # product_compare
        ("声岚 SL-NC700 和 声岚 SL-NC500 有什么区别？", Intent.PRODUCT_COMPARE),
        ("键川 KC87 和 键川 KC104 对比一下", Intent.PRODUCT_COMPARE),
        ("这两款哪个好", Intent.PRODUCT_COMPARE),
        # product_fact
        ("声岚 SL-BUDS Air 卖多少钱？", Intent.PRODUCT_FACT),
        ("键川 KC87 现在还有货吗？", Intent.PRODUCT_FACT),
        ("光影 GM-X2 的续航参数是多少", Intent.PRODUCT_FACT),
        ("SKU DEMO-HEAD-001-BLK 的价格", Intent.PRODUCT_FACT),
        # policy_faq
        ("七天无理由退货从什么时候开始计算？", Intent.POLICY_FAQ),
        ("退货运费由谁承担？", Intent.POLICY_FAQ),
        ("耳机保修期是多久？", Intent.POLICY_FAQ),
        ("订单满多少可以包邮？", Intent.POLICY_FAQ),
        ("退款多久能到账？", Intent.POLICY_FAQ),
        # order_status
        ("我的订单状态怎么样了", Intent.ORDER_STATUS),
        ("帮我查订单 DEMO-1001 的进度", Intent.ORDER_STATUS),
        ("订单号 DEMO-1001 支付成功了吗", Intent.ORDER_STATUS),
        # shipment
        ("我的订单 DEMO-1001 到哪了？", Intent.SHIPMENT),
        ("快递什么时候能到", Intent.SHIPMENT),
        ("物流一直没更新，能查一下吗", Intent.SHIPMENT),
        # return_eligibility
        ("这个订单的耳机尺码不合适，能退吗？", Intent.RETURN_ELIGIBILITY),
        ("我的订单符合退货条件吗？", Intent.RETURN_ELIGIBILITY),
        ("超过七天了还能退吗", Intent.RETURN_ELIGIBILITY),
        # return_request
        ("我要退货，怎么申请？", Intent.RETURN_REQUEST),
        ("帮我提交退货申请", Intent.RETURN_REQUEST),
        ("我想退货，尺码不合适", Intent.RETURN_REQUEST),
        # complaint_handoff
        ("我要投诉，你们太差了", Intent.COMPLAINT_HANDOFF),
        ("我要起诉你们，找律师", Intent.COMPLAINT_HANDOFF),
        ("转人工", Intent.COMPLAINT_HANDOFF),
        ("立刻给我退款", Intent.COMPLAINT_HANDOFF),
        # smalltalk_or_unknown
        ("你好", Intent.SMALLTALK_OR_UNKNOWN),
        ("谢谢你", Intent.SMALLTALK_OR_UNKNOWN),
        ("今天天气怎么样", Intent.SMALLTALK_OR_UNKNOWN),
    ],
)
def test_intent_routing(text: str, expected: Intent) -> None:
    route = route_intent(text, settings=SETTINGS)
    assert route.intent is expected, route.as_dict()


def test_all_ten_intents_are_reachable() -> None:
    assert {intent.value for intent in Intent} == {
        "product_discovery",
        "product_compare",
        "product_fact",
        "policy_faq",
        "order_status",
        "shipment",
        "return_eligibility",
        "return_request",
        "complaint_handoff",
        "smalltalk_or_unknown",
    }


def test_complaint_and_legal_take_precedence_and_keep_highest_risk() -> None:
    route = route_intent("我要投诉并起诉，要求立刻退款并赔偿", settings=SETTINGS)
    assert route.intent is Intent.COMPLAINT_HANDOFF
    assert route.risk.level is RiskLevel.CRITICAL
    assert route.risk.primary_reason_code == "LEGAL_OR_REGULATORY"
    assert route.handoff_required is True
    assert route.allowed_tools == ()


def test_money_demand_routes_to_handoff_not_a_write_tool() -> None:
    route = route_intent("现在直接给我退款，不然我就曝光", settings=SETTINGS)
    assert route.intent is Intent.COMPLAINT_HANDOFF
    assert route.handoff_required is True
    assert "MONEY_DECISION_REQUIRED" in route.risk.codes
    assert route.allowed_tools == ()


def test_high_value_return_requires_handoff_even_though_intent_is_return_request() -> None:
    route = route_intent("我要退货，这单商品 6000 元", settings=SETTINGS)
    assert route.intent is Intent.RETURN_REQUEST
    assert "HIGH_VALUE_ORDER" in route.risk.codes
    assert route.handoff_required is True
    assert route.allowed_tools == ()


@pytest.mark.parametrize("amount", ["6,000", "12,000", "5,000"])
def test_grouped_high_value_amount_still_requires_handoff(amount: str) -> None:
    """F1: "6,000 元" used to parse as 0 cents and silently skip the high-value rule."""
    route = route_intent(f"我要退货，这单商品 {amount} 元", settings=SETTINGS)
    assert route.intent is Intent.RETURN_REQUEST
    assert "HIGH_VALUE_ORDER" in route.risk.codes
    assert route.handoff_required is True
    assert route.allowed_tools == ()


def test_grouped_amount_below_the_threshold_does_not_hand_off() -> None:
    """The threshold still applies: 4,999 元 < 500,000 分 must not be escalated."""
    route = route_intent("这单 4,999 元要退货", settings=SETTINGS)
    assert route.intent is Intent.RETURN_REQUEST
    assert "HIGH_VALUE_ORDER" not in route.risk.codes
    assert route.handoff_required is False


def test_low_confidence_asks_for_clarification_without_tools() -> None:
    route = route_intent("帮我看看", settings=SETTINGS)
    assert route.intent is Intent.SMALLTALK_OR_UNKNOWN
    assert route.confidence < SETTINGS.intent_min_confidence
    assert route.requires_clarification is True
    assert route.path is RoutePath.SAFE_FALLBACK
    assert route.allowed_tools == ()
    assert route.clarification_text


def test_history_resolves_a_referential_follow_up() -> None:
    route = route_intent(
        "那它多少钱",
        history=("声岚 SL-NC300 入耳式降噪耳机 现在还有货吗？",),
        settings=SETTINGS,
    )
    assert route.intent is Intent.PRODUCT_FACT
    assert route.history_used is True
    assert route.confidence >= SETTINGS.intent_min_confidence
    assert route.allowed_tools


def test_explicit_current_intent_is_not_overridden_by_history() -> None:
    route = route_intent(
        "这个耳机多少钱",
        history=("我要投诉你们",),
        settings=SETTINGS,
    )
    assert route.intent is Intent.PRODUCT_FACT
    assert route.handoff_required is False


def test_policy_route_is_cache_eligible_only_without_order_identifiers() -> None:
    clean = route_intent("七天无理由退货怎么算？", settings=SETTINGS)
    assert clean.intent is Intent.POLICY_FAQ
    assert clean.cache_eligible is True

    with_order = route_intent("订单 DEMO-1001 的退款政策是什么", settings=SETTINGS)
    assert with_order.intent is Intent.POLICY_FAQ
    assert with_order.cache_eligible is False


def test_no_route_exposes_a_write_tool() -> None:
    """Stage 8 must not reach return/handoff writes; those are stage 9."""
    write_tools = {"create_return_request", "create_handoff_ticket"}
    for intent, tools in ALLOWED_TOOLS.items():
        assert not (set(tools) & write_tools), intent


def test_return_request_requires_an_eligibility_check_first() -> None:
    route = route_intent("帮我提交退货申请", settings=SETTINGS)
    assert route.intent is Intent.RETURN_REQUEST
    assert route.allowed_tools == ("check_return_eligibility",)


# -- complaint route must always escalate (stage-8 acceptance defect G3) ----


@pytest.mark.parametrize("text", ["太差了", "垃圾"])
def test_complaint_route_is_always_flagged_for_handoff(text: str) -> None:
    route = route_intent(text, settings=SETTINGS)
    assert route.intent is Intent.COMPLAINT_HANDOFF
    assert route.handoff_required is True
    assert route.allowed_tools == ()
    assert route.cache_eligible is False
    # the flag must survive serialisation for the SSE meta/audit record
    assert route.as_dict()["handoff_required"] is True


def test_normal_policy_route_keeps_handoff_false_and_stays_cacheable() -> None:
    route = route_intent("七天无理由退货运费谁承担", settings=SETTINGS)
    assert route.intent is Intent.POLICY_FAQ
    assert route.handoff_required is False
    assert route.cache_eligible is True


def test_referential_follow_up_never_yields_a_handoff_free_complaint_route() -> None:
    route = route_intent("那它呢", history=("我要投诉你们",), settings=SETTINGS)
    assert route.intent is Intent.COMPLAINT_HANDOFF
    assert route.history_used is True
    assert route.handoff_required is not False
    assert route.allowed_tools == ()


# -- policy question variants (stage-8 acceptance defect G6) ---------------


@pytest.mark.parametrize("text", ["那能退么", "那能退嘛", "能退么"])
def test_colloquial_return_question_is_not_smalltalk(text: str) -> None:
    route = route_intent(text, settings=SETTINGS)
    assert route.intent is Intent.RETURN_ELIGIBILITY, route.as_dict()
    assert route.requires_clarification is False
    assert route.allowed_tools == ("check_return_eligibility",)


# -- low-confidence policy route must not be cacheable ---------------------


def test_low_confidence_policy_route_is_not_cache_eligible() -> None:
    """A stricter request threshold leaves this policy turn below the confidence gate."""
    strict = Settings(_env_file=None, intent_min_confidence=0.80)  # type: ignore[call-arg]
    route = route_intent("退货政策", settings=strict)
    assert route.intent is Intent.POLICY_FAQ
    assert route.confidence < strict.intent_min_confidence
    assert route.cache_eligible is False

    with_order = route_intent("订单 DEMO-1001 的退款政策是什么", settings=SETTINGS)
    assert with_order.intent is Intent.POLICY_FAQ
    assert with_order.cache_eligible is False
