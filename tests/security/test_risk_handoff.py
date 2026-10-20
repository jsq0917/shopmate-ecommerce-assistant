"""Risk table: codes, severity, primary reason precedence and handoff thresholds."""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.safety.risk import (
    HIGH_VALUE_ORDER_CENTS,
    RiskLevel,
    RiskSignals,
    assess_risk,
)


@pytest.mark.parametrize(
    ("text", "code", "level"),
    [
        ("我要转人工", "USER_REQUESTS_HUMAN", RiskLevel.HIGH),
        ("我要投诉你们", "COMPLAINT", RiskLevel.HIGH),
        ("我要起诉你们", "LEGAL_OR_REGULATORY", RiskLevel.CRITICAL),
        ("你们威胁我的人身安全", "PERSONAL_SAFETY", RiskLevel.CRITICAL),
        ("我的账号被盗了", "PRIVACY_OR_ACCOUNT_TAKEOVER", RiskLevel.CRITICAL),
        ("立刻给我退款", "MONEY_DECISION_REQUIRED", RiskLevel.HIGH),
    ],
)
def test_text_rules_match_contract_codes(text: str, code: str, level: RiskLevel) -> None:
    assessment = assess_risk(text)
    assert code in assessment.codes
    assert assessment.level is level
    assert assessment.handoff_required is True


def test_legal_threat_outranks_complaint_for_primary_reason() -> None:
    assessment = assess_risk("我要投诉，并且已经找律师起诉")
    assert assessment.level is RiskLevel.CRITICAL
    assert assessment.primary_reason_code == "LEGAL_OR_REGULATORY"
    assert "COMPLAINT" in assessment.codes


def test_high_value_threshold_boundary() -> None:
    below = assess_risk("退货", signals=RiskSignals(amount_cents=HIGH_VALUE_ORDER_CENTS - 1))
    assert "HIGH_VALUE_ORDER" not in below.codes
    assert below.handoff_required is False

    at = assess_risk("退货", signals=RiskSignals(amount_cents=HIGH_VALUE_ORDER_CENTS))
    assert "HIGH_VALUE_ORDER" in at.codes
    assert at.handoff_required is True


def test_low_confidence_non_rights_is_medium_and_does_not_hand_off() -> None:
    assessment = assess_risk(
        "随便聊聊",
        signals=RiskSignals(intent="smalltalk_or_unknown", confidence=0.30),
    )
    assert "LOW_CONFIDENCE" in assessment.codes
    assert assessment.level is RiskLevel.MEDIUM
    assert assessment.handoff_required is False


def test_low_confidence_on_rights_is_high_and_hands_off() -> None:
    assessment = assess_risk(
        "那个能退吗",
        signals=RiskSignals(intent="return_eligibility", confidence=0.40),
    )
    assert assessment.level is RiskLevel.HIGH
    assert assessment.handoff_required is True
    assert "LOW_CONFIDENCE" in assessment.codes


@pytest.mark.parametrize(
    ("signal", "code"),
    [
        ("policy_conflict", "POLICY_CONFLICT"),
        ("insufficient_evidence_rights", "INSUFFICIENT_EVIDENCE_RIGHTS"),
        ("tool_failure_repeated", "TOOL_FAILURE_REPEATED"),
        ("tool_model_conflict", "TOOL_MODEL_CONFLICT"),
        ("output_guard_money", "OUTPUT_GUARD_MONEY"),
        ("output_guard_pii", "OUTPUT_GUARD_PII"),
        ("return_reason_requires_review", "RETURN_REASON_REQUIRES_REVIEW"),
    ],
)
def test_service_signals_map_to_contract_codes(signal: str, code: str) -> None:
    assessment = assess_risk("退款", signals=RiskSignals(**{signal: True}))
    assert code in assessment.codes
    assert assessment.handoff_required is True


def test_abnormal_order_pattern_is_medium_by_default() -> None:
    assessment = assess_risk("查订单", signals=RiskSignals(abnormal_order_pattern=True))
    assert "ABNORMAL_ORDER_PATTERN" in assessment.codes
    assert assessment.level is RiskLevel.MEDIUM
    assert assessment.handoff_required is False


def test_policy_description_of_a_refund_is_not_a_money_demand() -> None:
    assessment = assess_risk("退款一般多久能到账？")
    assert "MONEY_DECISION_REQUIRED" not in assessment.codes
    assert assessment.level is RiskLevel.LOW


def test_assessment_payload_is_json_ready() -> None:
    payload = assess_risk("我要投诉").as_dict()
    assert payload["risk_level"] == "high"
    assert "COMPLAINT" in payload["risk_codes"]
    assert payload["primary_reason_code"] == "COMPLAINT"
