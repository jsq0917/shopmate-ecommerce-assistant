"""Unit tests for risk resolution and queue priority (docs/05-tool-contract.md §7.3)."""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.domain.handoff.rules import (
    ResolvedRisk,
    resolve_risk,
)
from shopmate_ecommerce_assistant.safety.risk import RiskLevel


def test_critical_reason_maps_priority_1() -> None:
    resolved = resolve_risk("LEGAL_OR_REGULATORY")
    assert resolved.level is RiskLevel.CRITICAL
    assert resolved.priority == 1
    assert resolved.queue == "priority_support"
    assert resolved.primary_reason_code == "LEGAL_OR_REGULATORY"


def test_high_reason_maps_priority_2() -> None:
    assert resolve_risk("COMPLAINT").priority == 2


def test_context_level_is_never_downgraded() -> None:
    resolved = resolve_risk(
        "COMPLAINT", context_level=RiskLevel.CRITICAL, context_codes=("PERSONAL_SAFETY",)
    )
    assert resolved.level is RiskLevel.CRITICAL
    assert resolved.primary_reason_code == "PERSONAL_SAFETY"
    assert "COMPLAINT" in resolved.reason_codes


def test_context_cannot_raise_an_unknown_code() -> None:
    resolved = resolve_risk("COMPLAINT", context_codes=("NOT_A_REAL_CODE",))
    assert "NOT_A_REAL_CODE" not in resolved.reason_codes


def test_unknown_reason_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_risk("FAKE_RISK")


def test_reason_codes_are_ordered_by_contract() -> None:
    resolved = resolve_risk("COMPLAINT", context_codes=("LEGAL_OR_REGULATORY",))
    # LEGAL_OR_REGULATORY (critical) beats COMPLAINT (high) as primary.
    assert resolved.primary_reason_code == "LEGAL_OR_REGULATORY"
    assert resolved.level is RiskLevel.CRITICAL


def test_primary_is_included_in_codes() -> None:
    resolved = resolve_risk("COMPLAINT", context_codes=("MONEY_DECISION_REQUIRED",))
    assert resolved.primary_reason_code in resolved.reason_codes


def test_low_confidence_defaults_medium() -> None:
    resolved = resolve_risk("LOW_CONFIDENCE")
    assert resolved.level is RiskLevel.MEDIUM
    assert resolved.priority == 3


def test_result_is_immutable_dataclass() -> None:
    assert isinstance(resolve_risk("COMPLAINT"), ResolvedRisk)
