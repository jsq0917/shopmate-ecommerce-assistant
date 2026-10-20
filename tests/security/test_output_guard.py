"""Output guard: PII, prompt leakage, citations, money promises, real-time facts."""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.rag.policy_qa import SYSTEM_PROMPT
from shopmate_ecommerce_assistant.safety.output_guard import (
    MONEY_COMMITMENT_TEXT,
    PROMPT_LEAK_TEXT,
    UNCITED_POLICY_TEXT,
    UNVERIFIED_FACT_TEXT,
    OutputAction,
    guard_output,
)


def test_cited_policy_answer_passes() -> None:
    result = guard_output(
        "自签收之日起七日内可申请无理由退货[c1]。",
        intent="policy_faq",
        citation_labels=("c1",),
    )
    assert result.allowed is True
    assert result.action is OutputAction.PASS
    assert result.issues == ()


def test_uncited_policy_claim_is_blocked() -> None:
    result = guard_output(
        "退货期限为七天，运费由消费者承担。",
        intent="policy_faq",
        citation_labels=("c1",),
    )
    assert result.allowed is False
    assert result.text == UNCITED_POLICY_TEXT
    assert "missing_citation" in result.issues or "uncited_claim" in result.issues
    assert "INSUFFICIENT_EVIDENCE_RIGHTS" in result.risk_codes


def test_unknown_citation_label_is_blocked() -> None:
    result = guard_output(
        "退货期限为七天[c9]。",
        intent="policy_faq",
        citation_labels=("c1",),
    )
    assert result.allowed is False
    assert any(issue.startswith("unknown_citation:") for issue in result.issues)


def test_fixed_refusal_text_is_not_treated_as_an_uncited_claim() -> None:
    result = guard_output(
        "当前知识库中没有足够依据回答这个问题。为避免给出不准确的条款，我不会猜测。",
        intent="policy_faq",
        citation_labels=(),
    )
    assert result.allowed is True


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        # Chat-path deterministic degradations (chat_service.POLICY_UNAVAILABLE_TEXT /
        # UPSTREAM_TEXT) must reach the user verbatim instead of being relabelled as an
        # uncited model claim, which would hide the real reason and force a handoff.
        (
            "当前知识库暂不可用，无法确认政策依据，请转人工客服核实。",
            "policy_faq",
        ),
        (
            "当前无法确认最新信息，请稍后重试或转人工协助。",
            "policy_faq",
        ),
    ],
)
def test_chat_degradation_texts_pass_the_guard(text: str, intent: str) -> None:
    result = guard_output(text, intent=intent, citation_labels=None)
    assert result.allowed is True
    assert result.text == text
    assert result.handoff_required is False


def test_completed_refund_is_blocked() -> None:
    result = guard_output("已为您退款，请查收。", intent=None)
    assert result.allowed is False
    assert result.text == MONEY_COMMITMENT_TEXT
    assert "OUTPUT_GUARD_MONEY" in result.risk_codes
    assert result.handoff_required is True


def test_future_refund_promise_is_blocked() -> None:
    result = guard_output("我们会在审核通过后为您退款。", intent=None)
    assert result.allowed is False
    assert result.text == MONEY_COMMITMENT_TEXT


def test_negated_refund_is_not_a_commitment() -> None:
    result = guard_output("我们不会为您退款，需要人工审核。", intent=None)
    assert result.allowed is True
    assert result.action is OutputAction.PASS


def test_pii_is_redacted_before_display() -> None:
    result = guard_output("请联系 13812345678 处理。", intent=None)
    assert result.allowed is True
    assert result.action is OutputAction.REDACT
    assert "13812345678" not in result.text
    assert "138****5678" in result.text
    assert result.handoff_required is True
    assert "OUTPUT_GUARD_PII" in result.risk_codes


def test_full_system_prompt_is_blocked() -> None:
    result = guard_output(SYSTEM_PROMPT, intent=None)
    assert result.allowed is False
    assert result.text == PROMPT_LEAK_TEXT
    assert "system_prompt_leak" in result.issues


def test_refusing_to_share_the_prompt_is_not_a_leak() -> None:
    result = guard_output("我无法提供系统提示或内部规则。", intent=None)
    assert result.allowed is True


def test_price_without_tool_evidence_is_blocked() -> None:
    result = guard_output(
        "这款耳机售价 299 元，现在有货。",
        intent="product_fact",
        structured_facts_verified=False,
    )
    assert result.allowed is False
    assert result.text == UNVERIFIED_FACT_TEXT
    assert "unverified_realtime_fact" in result.issues


def test_price_with_tool_evidence_passes() -> None:
    result = guard_output(
        "这款耳机售价 299 元，现在有货，数据更新于 2026-10-19T12:00:00Z。",
        intent="product_fact",
        structured_facts_verified=True,
    )
    assert result.allowed is True
    assert result.action is OutputAction.PASS


def test_unsafe_html_and_external_link_are_removed() -> None:
    result = guard_output(
        "详情见 <script>alert(1)</script> https://evil.example/pay",
        intent=None,
    )
    assert result.allowed is True
    assert result.action is OutputAction.SANITIZE
    assert "<script>" not in result.text
    assert "https://evil.example" not in result.text
    assert "unsafe_link_removed" in result.issues


@pytest.mark.parametrize(
    "text",
    ["保证退款", "百分百能退", "我们承诺赔偿", "假一赔十"],
)
def test_other_money_promise_phrasings_are_blocked(text: str) -> None:
    result = guard_output(text, intent=None)
    assert result.allowed is False
    assert result.text == MONEY_COMMITMENT_TEXT
