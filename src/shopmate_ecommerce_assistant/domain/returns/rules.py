"""Deterministic return-eligibility rules, version ``demo-return-v1``.

The rule table mirrors ``docs/05-tool-contract.md`` §7.1 in the same priority order: the
first matching rule decides, and every rule evaluated before it is reported in
``matched_rule_codes`` so an answer can explain *why*.

Two invariants are enforced by construction, not by the caller:

* the deadline is always ``order_items.delivered_at + 7 days`` (never "today + 7 days");
* only the terminal branch ``RETURN_ELIGIBLE`` allows a write, so a decision of
  ``needs_manual_review`` can never produce a submitted application.

This module is pure: no I/O, no clock, no database. ``now`` is injected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    ReturnReasonCode,
)
from shopmate_ecommerce_assistant.safety.risk import HIGH_VALUE_ORDER_CENTS

RULE_VERSION = "demo-return-v1"
RETURN_WINDOW_DAYS = 7

#: Reasons a shopper can submit without human review.
SELF_SERVICE_REASONS: frozenset[ReturnReasonCode] = frozenset(
    {ReturnReasonCode.SIZE_OR_FIT, ReturnReasonCode.NO_LONGER_NEEDED}
)

#: Reasons that always need a human to look at evidence.
MANUAL_REVIEW_REASONS: frozenset[ReturnReasonCode] = frozenset(
    {
        ReturnReasonCode.DAMAGED_ON_ARRIVAL,
        ReturnReasonCode.WRONG_ITEM,
        ReturnReasonCode.QUALITY_ISSUE,
        ReturnReasonCode.OTHER,
    }
)

# Stable rule codes. They are reported to the caller and stored in audit summaries, so
# renaming one is a contract change.
R_ORDER_DELIVERED = "ORDER_DELIVERED"
R_ORDER_NOT_DELIVERED = "ORDER_NOT_DELIVERED"
R_ORDER_CANCELLED = "ORDER_CANCELLED"
R_ITEM_ACTIVE = "ITEM_ACTIVE"
R_ITEM_NOT_ACTIVE = "ITEM_NOT_ACTIVE"
R_ITEM_RETURNABLE = "ITEM_RETURNABLE"
R_ITEM_NOT_RETURNABLE = "ITEM_NOT_RETURNABLE"
R_NO_ACTIVE_RETURN = "NO_ACTIVE_RETURN"
R_DUPLICATE_ACTIVE_RETURN = "DUPLICATE_ACTIVE_RETURN"
R_REASON_SELF_SERVICE = "REASON_IN_WINDOW"
R_REASON_REQUIRES_REVIEW = "REASON_REQUIRES_REVIEW"
R_ITEM_DELIVERED = "ITEM_DELIVERED"
R_ITEM_NOT_DELIVERED = "ITEM_NOT_DELIVERED"
R_WITHIN_WINDOW = "WITHIN_7_DAYS"
R_WINDOW_EXPIRED = "RETURN_WINDOW_EXPIRED"
R_BELOW_HIGH_VALUE = "BELOW_HIGH_VALUE"
R_HIGH_VALUE = "HIGH_VALUE_ORDER"
R_LOW_CONFIDENCE_FIRST = "LOW_CONFIDENCE_FIRST"
R_LOW_CONFIDENCE_REPEATED = "LOW_CONFIDENCE_REPEATED"
R_ELIGIBLE = "RETURN_ELIGIBLE"

_MATERIALS: dict[ReturnReasonCode, tuple[str, ...]] = {
    ReturnReasonCode.SIZE_OR_FIT: ("商品及包装完好", "退货原因说明"),
    ReturnReasonCode.NO_LONGER_NEEDED: ("商品及包装完好", "退货原因说明"),
    ReturnReasonCode.DAMAGED_ON_ARRIVAL: ("问题照片或视频", "商品及包装保留", "退货原因说明"),
    ReturnReasonCode.WRONG_ITEM: ("收到的商品照片", "商品及包装保留", "退货原因说明"),
    ReturnReasonCode.QUALITY_ISSUE: ("问题照片或视频", "商品及包装保留", "退货原因说明"),
    ReturnReasonCode.OTHER: ("退货原因说明", "商品及包装完好"),
}


class ReturnDecision(StrEnum):
    """The four business outcomes of an eligibility check."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


@dataclass(frozen=True, slots=True)
class ReturnCheck:
    """Every fact the rule table needs, already scoped to the authenticated user."""

    order_status: OrderStatus
    item_status: OrderItemStatus
    is_returnable: bool
    item_delivered_at: datetime | None
    line_total_cents: int
    reason_code: ReturnReasonCode
    has_active_return: bool
    now: datetime
    confidence: float | None = None
    clarification_attempted: bool = False
    low_confidence_threshold: float = 0.70


@dataclass(frozen=True, slots=True)
class ReturnEvaluation:
    """The rule outcome plus everything an answer or an audit needs to explain it."""

    decision: ReturnDecision
    decision_code: str
    matched_rule_codes: tuple[str, ...]
    deadline_at: datetime | None
    required_materials: tuple[str, ...]
    handoff_reason_code: str | None = None

    @property
    def eligible(self) -> bool:
        return self.decision is ReturnDecision.ELIGIBLE

    @property
    def needs_clarification(self) -> bool:
        return self.decision is ReturnDecision.NEEDS_CLARIFICATION

    @property
    def needs_manual_review(self) -> bool:
        return self.decision is ReturnDecision.NEEDS_MANUAL_REVIEW

    @property
    def can_create_return_request(self) -> bool:
        """Only an eligible decision may be turned into a write."""
        return self.eligible

    @property
    def handoff_required(self) -> bool:
        return self.needs_manual_review

    @property
    def next_action(self) -> str:
        if self.eligible:
            return "confirm_to_submit"
        if self.needs_clarification:
            return "clarify_reason"
        if self.needs_manual_review:
            return "handoff_to_human"
        return "explain_rules"


def return_deadline(delivered_at: datetime) -> datetime:
    """Return the inclusive last instant of the return window."""
    return delivered_at + timedelta(days=RETURN_WINDOW_DAYS)


def materials_for(reason_code: ReturnReasonCode) -> tuple[str, ...]:
    """Return the material checklist the shopper must prepare."""
    return _MATERIALS[reason_code]


def _result(
    check: ReturnCheck,
    decision: ReturnDecision,
    code: str,
    codes: list[str],
    *,
    deadline: datetime | None,
    handoff_reason_code: str | None = None,
) -> ReturnEvaluation:
    return ReturnEvaluation(
        decision=decision,
        decision_code=code,
        matched_rule_codes=tuple(codes),
        deadline_at=deadline,
        required_materials=_MATERIALS[check.reason_code],
        handoff_reason_code=handoff_reason_code,
    )


def evaluate_return(check: ReturnCheck) -> ReturnEvaluation:
    """Apply ``demo-return-v1`` and return the first matching decision."""
    deadline = (
        return_deadline(check.item_delivered_at) if check.item_delivered_at is not None else None
    )
    codes: list[str] = []

    # Priority 2/3: unsure about the reason means no write, and a second failure means a
    # human. The router already escalates low confidence on rights intents; the tool must
    # still refuse to create anything when it is unsure.
    if check.confidence is not None and check.confidence < check.low_confidence_threshold:
        if check.clarification_attempted:
            codes.append(R_LOW_CONFIDENCE_REPEATED)
            return _result(
                check,
                ReturnDecision.NEEDS_MANUAL_REVIEW,
                "LOW_CONFIDENCE",
                codes,
                deadline=deadline,
                handoff_reason_code="LOW_CONFIDENCE",
            )
        codes.append(R_LOW_CONFIDENCE_FIRST)
        return _result(
            check,
            ReturnDecision.NEEDS_CLARIFICATION,
            "LOW_CONFIDENCE",
            codes,
            deadline=deadline,
        )

    # Priority 4/5: only a finished delivery can be returned; a cancelled order cannot.
    if check.order_status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
        codes.append(R_ORDER_DELIVERED)
    elif check.order_status is OrderStatus.CANCELLED:
        codes.append(R_ORDER_CANCELLED)
        return _result(
            check, ReturnDecision.INELIGIBLE, "RETURN_NOT_ALLOWED", codes, deadline=deadline
        )
    else:
        codes.append(R_ORDER_NOT_DELIVERED)
        return _result(check, ReturnDecision.INELIGIBLE, "INVALID_STATE", codes, deadline=deadline)

    # Priority 6: the line itself must still be active.
    if check.item_status is not OrderItemStatus.ACTIVE:
        codes.append(R_ITEM_NOT_ACTIVE)
        return _result(check, ReturnDecision.INELIGIBLE, "INVALID_STATE", codes, deadline=deadline)
    codes.append(R_ITEM_ACTIVE)

    # Priority 7: category snapshot decides returnability, not the current catalog.
    if not check.is_returnable:
        codes.append(R_ITEM_NOT_RETURNABLE)
        return _result(
            check, ReturnDecision.INELIGIBLE, "RETURN_NOT_ALLOWED", codes, deadline=deadline
        )
    codes.append(R_ITEM_RETURNABLE)

    # Priority 8: at most one active application per order item, any reason.
    if check.has_active_return:
        codes.append(R_DUPLICATE_ACTIVE_RETURN)
        return _result(
            check, ReturnDecision.INELIGIBLE, "DUPLICATE_RETURN", codes, deadline=deadline
        )
    codes.append(R_NO_ACTIVE_RETURN)

    # Priority 9: damage, wrong item, quality and "other" need evidence review.
    if check.reason_code in MANUAL_REVIEW_REASONS:
        codes.append(R_REASON_REQUIRES_REVIEW)
        return _result(
            check,
            ReturnDecision.NEEDS_MANUAL_REVIEW,
            "MANUAL_REVIEW_REQUIRED",
            codes,
            deadline=deadline,
            handoff_reason_code="RETURN_REASON_REQUIRES_REVIEW",
        )
    codes.append(R_REASON_SELF_SERVICE)

    # Priority 10/11: the window starts at signature, not at checkout.
    if check.item_delivered_at is None:
        codes.append(R_ITEM_NOT_DELIVERED)
        return _result(check, ReturnDecision.INELIGIBLE, "INVALID_STATE", codes, deadline=deadline)
    codes.append(R_ITEM_DELIVERED)

    # ``now <= deadline`` is inside the window; one second later is outside.
    if deadline is not None and check.now > deadline:
        codes.append(R_WINDOW_EXPIRED)
        return _result(
            check, ReturnDecision.INELIGIBLE, "RETURN_WINDOW_EXPIRED", codes, deadline=deadline
        )
    codes.append(R_WITHIN_WINDOW)

    # Priority 12: large amounts need a human even when everything else passes.
    if check.line_total_cents >= HIGH_VALUE_ORDER_CENTS:
        codes.append(R_HIGH_VALUE)
        return _result(
            check,
            ReturnDecision.NEEDS_MANUAL_REVIEW,
            "MANUAL_REVIEW_REQUIRED",
            codes,
            deadline=deadline,
            handoff_reason_code="HIGH_VALUE_ORDER",
        )
    codes.append(R_BELOW_HIGH_VALUE)

    codes.append(R_ELIGIBLE)
    return _result(check, ReturnDecision.ELIGIBLE, "RETURN_ELIGIBLE", codes, deadline=deadline)


__all__ = [
    "MANUAL_REVIEW_REASONS",
    "RETURN_WINDOW_DAYS",
    "RULE_VERSION",
    "SELF_SERVICE_REASONS",
    "ReturnCheck",
    "ReturnDecision",
    "ReturnEvaluation",
    "evaluate_return",
    "materials_for",
    "return_deadline",
]
