"""Unit tests for the ``demo-return-v1`` rule table (docs/05-tool-contract.md §7.1)."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    ReturnReasonCode,
    ReturnStatus,
)
from shopmate_ecommerce_assistant.domain.orders.models import ActiveReturnSnapshot
from shopmate_ecommerce_assistant.domain.returns.rules import (
    RETURN_WINDOW_DAYS,
    ReturnCheck,
    ReturnDecision,
    evaluate_return,
    return_deadline,
)

NOW = datetime(2026, 10, 15, 8, 0, 0)
DELIVERED_AT = datetime(2026, 10, 12, 8, 0, 0)


def _check(**overrides) -> ReturnCheck:
    base = dict(
        order_status=OrderStatus.DELIVERED,
        item_status=OrderItemStatus.ACTIVE,
        is_returnable=True,
        item_delivered_at=DELIVERED_AT,
        line_total_cents=29_900,
        reason_code=ReturnReasonCode.SIZE_OR_FIT,
        has_active_return=False,
        now=NOW,
    )
    base.update(overrides)
    return ReturnCheck(**base)


def test_eligible_when_all_rules_pass() -> None:
    result = evaluate_return(_check())
    assert result.decision is ReturnDecision.ELIGIBLE
    assert result.decision_code == "RETURN_ELIGIBLE"
    assert result.eligible is True
    assert result.can_create_return_request is True
    assert result.handoff_required is False
    assert result.matched_rule_codes[-1] == "RETURN_ELIGIBLE"
    assert result.deadline_at == return_deadline(DELIVERED_AT)


@pytest.mark.parametrize(
    "order_status,decision_code",
    [
        (OrderStatus.CREATED, "INVALID_STATE"),
        (OrderStatus.PAID, "INVALID_STATE"),
        (OrderStatus.PROCESSING, "INVALID_STATE"),
        (OrderStatus.SHIPPED, "INVALID_STATE"),
    ],
)
def test_order_not_delivered_blocks(order_status, decision_code) -> None:
    result = evaluate_return(_check(order_status=order_status))
    assert result.decision is ReturnDecision.INELIGIBLE
    assert result.decision_code == decision_code
    assert result.can_create_return_request is False


def test_cancelled_order_is_not_allowed() -> None:
    result = evaluate_return(_check(order_status=OrderStatus.CANCELLED))
    assert result.decision_code == "RETURN_NOT_ALLOWED"
    assert "ORDER_CANCELLED" in result.matched_rule_codes


@pytest.mark.parametrize("status", [OrderItemStatus.CANCELLED, OrderItemStatus.RETURNED])
def test_non_active_item_blocks(status) -> None:
    result = evaluate_return(_check(item_status=status))
    assert result.decision_code == "INVALID_STATE"


def test_non_returnable_category_blocks() -> None:
    result = evaluate_return(_check(is_returnable=False))
    assert result.decision_code == "RETURN_NOT_ALLOWED"
    assert "ITEM_NOT_RETURNABLE" in result.matched_rule_codes


def test_duplicate_active_return_blocks() -> None:
    result = evaluate_return(_check(has_active_return=True))
    assert result.decision_code == "DUPLICATE_RETURN"


# ------------------------------------------------- ``已退款 / 已退货`` 口径（§16.2.2）
#
# 数据契约没有订单级 ``refunded`` 状态（docs/04-data-contract.md §6.1），"已退款"在本项目
# 的等价语义有两种落地方式：
#   1. ``order_items.status = returned``（该笔已退回）；
#   2. ``return_requests.status = completed``（退货已走完）。
# 下面三条用例分别钉住这两种语义在规则层与仓库层的表现。


def test_returned_item_is_never_eligible() -> None:
    """已退货的商品行不得再次申请（``order_item.status=returned`` 即“已退款”口径）。"""
    result = evaluate_return(_check(item_status=OrderItemStatus.RETURNED))
    assert result.decision is ReturnDecision.INELIGIBLE
    assert result.decision_code == "INVALID_STATE"
    assert result.can_create_return_request is False


@pytest.mark.parametrize(
    "status",
    [ReturnStatus.SUBMITTED, ReturnStatus.UNDER_REVIEW, ReturnStatus.APPROVED],
    ids=["submitted", "under_review", "approved"],
)
def test_each_open_return_status_blocks_a_duplicate(status) -> None:
    """任一未结束的申请都阻断新申请，与 ``reason_code`` 无关。

    规则层只看到 ``has_active_return`` 这一个布尔值；把状态映射成该布尔值的责任在仓库层
    （见 ``tests/integration/test_order_return_handoff_db.py`` 的
    ``test_completed_return_still_blocks_a_new_application``）。
    """
    existing = ActiveReturnSnapshot(
        id=uuid4(),
        status=status,
        reason_code=ReturnReasonCode.SIZE_OR_FIT.value,
        requested_at=DELIVERED_AT,
    )
    result = evaluate_return(_check(has_active_return=existing is not None))
    assert result.decision is ReturnDecision.INELIGIBLE
    assert result.decision_code == "DUPLICATE_RETURN"
    assert result.can_create_return_request is False


def test_completed_order_with_active_item_stays_eligible_at_rule_level() -> None:
    """订单 ``completed`` 本身不阻断：它只表示订单终态，不代表已退货。

    实测结论（阶段 12 验收后修复，2026-10-20）：``order_status=completed`` +
    ``item_status=active`` + 窗口内 → ``RETURN_ELIGIBLE``。因此"退货已完成后再申请"的
    阻断不能靠订单状态，必须由仓库层的 ``find_active_return`` 把
    ``return_requests.status=completed`` 视为阻断记录（见
    ``db/repositories/orders.py`` 的 ``_CLOSED_RETURN_STATUSES``）。
    """
    result = evaluate_return(_check(order_status=OrderStatus.COMPLETED))
    assert result.decision is ReturnDecision.ELIGIBLE
    assert result.decision_code == "RETURN_ELIGIBLE"
    assert result.can_create_return_request is True


@pytest.mark.parametrize(
    "reason_code",
    [
        ReturnReasonCode.DAMAGED_ON_ARRIVAL,
        ReturnReasonCode.WRONG_ITEM,
        ReturnReasonCode.QUALITY_ISSUE,
        ReturnReasonCode.OTHER,
    ],
)
def test_manual_review_reasons(reason_code) -> None:
    result = evaluate_return(_check(reason_code=reason_code))
    assert result.decision is ReturnDecision.NEEDS_MANUAL_REVIEW
    assert result.decision_code == "MANUAL_REVIEW_REQUIRED"
    assert result.handoff_required is True
    assert result.handoff_reason_code == "RETURN_REASON_REQUIRES_REVIEW"
    assert result.can_create_return_request is False


def test_not_delivered_item_blocks() -> None:
    result = evaluate_return(_check(item_delivered_at=None))
    assert result.decision_code == "INVALID_STATE"
    assert result.deadline_at is None


def test_window_boundary_exactly_deadline_is_eligible() -> None:
    deadline = return_deadline(DELIVERED_AT)
    assert evaluate_return(_check(now=deadline)).decision is ReturnDecision.ELIGIBLE


def test_window_one_second_after_deadline_expires() -> None:
    deadline = return_deadline(DELIVERED_AT)
    result = evaluate_return(_check(now=deadline + timedelta(seconds=1)))
    assert result.decision is ReturnDecision.INELIGIBLE
    assert result.decision_code == "RETURN_WINDOW_EXPIRED"
    assert result.deadline_at == deadline


@pytest.mark.parametrize(
    "amount_cents,expected",
    [
        (499_999, "RETURN_ELIGIBLE"),
        (500_000, "MANUAL_REVIEW_REQUIRED"),
        (500_001, "MANUAL_REVIEW_REQUIRED"),
    ],
)
def test_high_value_threshold(amount_cents, expected) -> None:
    result = evaluate_return(_check(line_total_cents=amount_cents))
    assert result.decision_code == expected
    if expected == "MANUAL_REVIEW_REQUIRED":
        assert result.handoff_reason_code == "HIGH_VALUE_ORDER"


def test_low_confidence_first_is_clarification() -> None:
    result = evaluate_return(_check(confidence=0.5))
    assert result.decision is ReturnDecision.NEEDS_CLARIFICATION
    assert result.decision_code == "LOW_CONFIDENCE"
    assert result.handoff_required is False


def test_low_confidence_repeated_is_manual_review() -> None:
    result = evaluate_return(_check(confidence=0.5, clarification_attempted=True))
    assert result.decision is ReturnDecision.NEEDS_MANUAL_REVIEW
    assert result.decision_code == "LOW_CONFIDENCE"
    assert result.handoff_required is True
    assert result.handoff_reason_code == "LOW_CONFIDENCE"


def test_self_service_reasons_pass_window_and_amount() -> None:
    result = evaluate_return(_check(reason_code=ReturnReasonCode.NO_LONGER_NEEDED))
    assert result.decision is ReturnDecision.ELIGIBLE


def test_deadline_is_delivered_plus_window() -> None:
    assert return_deadline(DELIVERED_AT) == DELIVERED_AT + timedelta(days=RETURN_WINDOW_DAYS)


def test_required_materials_present_for_every_decision() -> None:
    for reason in ReturnReasonCode:
        result = evaluate_return(_check(reason_code=reason))
        assert result.required_materials, reason
