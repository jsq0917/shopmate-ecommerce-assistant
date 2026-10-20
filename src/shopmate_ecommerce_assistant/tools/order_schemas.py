"""Strict schemas for the stage-9 order, return and handoff tools.

``extra="forbid"`` is the first line of defence: a model that tries to send ``user_id``,
``shop_id``, ``risk_level``, ``confirmation_state``, ``idempotency_key`` or the router's
``confidence``/``clarification_attempted`` gets a validation error instead of a silently
injected value. The server-injected ``idempotency_key`` is still validated by
``validate_idempotency_key`` (safe charset, no PII) before it reaches the write path.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopmate_ecommerce_assistant.db.models.enums import ReturnReasonCode
from shopmate_ecommerce_assistant.domain.handoff.rules import is_canonical_reason_code

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
MAX_HANDOFF_SUMMARY_CHARS = 500
MIN_TOKEN_CHARS = 16
MAX_TOKEN_CHARS = 4096

#: Strict PII shapes a key must never contain. The full free-text PII detector is too
#: loose here (a ten-digit run like ``0000000003`` is not a phone number), so only the two
#: unambiguous patterns — a mobile number and an 18-digit ID card — are rejected.
_MOBILE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(
    r"(?<![0-9A-Za-z])[1-9]\d{5}(?:19|20)\d{2}"
    r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])"
)

DecisionValue = Literal["eligible", "ineligible", "needs_clarification", "needs_manual_review"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_idempotency_key(value: str | None) -> str:
    """Validate a server-injected idempotency key (contract §8.2).

    The key must be 16-128 chars of ``[A-Za-z0-9._:-]`` and must not contain a mobile
    number or an 18-digit ID card. Raises ``ValueError`` otherwise; callers map this to a
    safe ``ToolError``.
    """
    if not value:
        raise ValueError("缺少幂等键")
    key = value.strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise ValueError("幂等键必须为 16-128 位的字母、数字或 . _ : - 字符")
    if _MOBILE_PHONE.search(key) or _ID_CARD.search(key):
        raise ValueError("幂等键不能包含手机号或身份证号")
    return key


class GetOrderStatusInput(_Strict):
    """Input of ``get_order_status``: exactly one of ``order_id`` / ``order_no``."""

    order_id: UUID | None = None
    order_no: str | None = Field(default=None, max_length=40)

    @field_validator("order_no")
    @classmethod
    def _clean_order_no(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _exactly_one_reference(self) -> Self:
        if (self.order_id is None) == (self.order_no is None):
            raise ValueError("order_id 与 order_no 必须二选一")
        return self


class OrderStatusEvent(_Strict):
    """One known order timestamp. Only real timestamps are reported."""

    status: str
    occurred_at: datetime


class OrderStatusData(_Strict):
    """Payload of a successful ``get_order_status`` call."""

    order_id: UUID
    order_no: str
    status: str
    total_cents: int
    currency: str
    is_synthetic: bool
    placed_at: datetime
    status_updated_at: datetime
    timeline: list[OrderStatusEvent]


class GetShipmentInput(_Strict):
    """Input of ``get_shipment``."""

    order_id: UUID


class ShipmentEventItem(_Strict):
    """One logistics node."""

    status: str
    description: str
    occurred_at: datetime


class GetShipmentData(_Strict):
    """Payload of a successful ``get_shipment`` call."""

    order_id: UUID
    shipment_id: UUID
    carrier: str
    tracking_no_masked: str
    status: str
    is_synthetic: bool
    shipped_at: datetime | None
    estimated_delivery_at: datetime | None
    delivered_at: datetime | None
    status_updated_at: datetime
    events: list[ShipmentEventItem]


class CheckReturnEligibilityInput(_Strict):
    """Input of ``check_return_eligibility``.

    The router's confidence and clarification state are server-injected via ``ToolContext``
    (``route_confidence`` / ``clarification_attempted``), never model payload, so the model
    cannot forge a low-confidence path.
    """

    order_id: UUID
    order_item_id: UUID
    reason_code: ReturnReasonCode


class ExistingReturnSummary(_Strict):
    """The application that blocks a duplicate."""

    return_request_id: UUID
    status: str
    reason_code: str
    requested_at: datetime


class CheckReturnEligibilityData(_Strict):
    """Payload of a ``check_return_eligibility`` call, including refusals."""

    decision: DecisionValue
    decision_code: str
    error_code: str | None
    eligible: bool
    needs_clarification: bool
    needs_manual_review: bool
    can_create_return_request: bool
    handoff_required: bool
    matched_rule_codes: list[str]
    deadline_at: datetime | None
    rule_version: str
    required_materials: list[str]
    next_action: str
    eligibility_token: str | None
    eligibility_expires_at: datetime | None
    evaluated_at: datetime
    handoff_reason_code: str | None = None
    existing_return: ExistingReturnSummary | None = None


class CreateReturnRequestInput(_Strict):
    """Input of ``create_return_request``; the token proves a prior eligible check.

    ``idempotency_key`` is not accepted here: it is injected by the API ``Idempotency-Key``
    header or a server-side operation id (contract §5.9).
    """

    order_id: UUID
    order_item_id: UUID
    reason_code: ReturnReasonCode
    eligibility_token: str = Field(min_length=MIN_TOKEN_CHARS, max_length=MAX_TOKEN_CHARS)


class CreateReturnRequestData(_Strict):
    """Payload of a successful return application."""

    return_request_id: UUID
    status: Literal["submitted"]
    submitted_at: datetime
    review_required: bool
    required_materials: list[str]
    next_action: str
    refund_status: Literal["not_created"]
    notice: str


class CreateHandoffTicketInput(_Strict):
    """Input of ``create_handoff_ticket``; risk level is server-side only.

    ``idempotency_key`` is not accepted here: it is injected by the API ``Idempotency-Key``
    header or a server-side operation id (contract §5.10).
    """

    conversation_id: UUID
    reason_code: str = Field(min_length=2, max_length=80)
    summary_redacted: str = Field(min_length=1, max_length=MAX_HANDOFF_SUMMARY_CHARS)

    @field_validator("reason_code")
    @classmethod
    def _canonical_reason(cls, value: str) -> str:
        code = value.strip().upper()
        if not is_canonical_reason_code(code):
            raise ValueError("不支持的风险原因码")
        return code

    @field_validator("summary_redacted")
    @classmethod
    def _summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("转人工摘要不能为空")
        return stripped


class CreateHandoffTicketData(_Strict):
    """Payload of a successful escalation."""

    ticket_id: UUID
    status: Literal["open"]
    risk_level: str
    priority: int
    queue: str
    primary_reason_code: str
    reason_codes: list[str]
    expected_response: str
    created_at: datetime


__all__ = [
    "CheckReturnEligibilityData",
    "CheckReturnEligibilityInput",
    "CreateHandoffTicketData",
    "CreateHandoffTicketInput",
    "CreateReturnRequestData",
    "CreateReturnRequestInput",
    "ExistingReturnSummary",
    "GetOrderStatusInput",
    "GetShipmentData",
    "GetShipmentInput",
    "IDEMPOTENCY_KEY_PATTERN",
    "MAX_HANDOFF_SUMMARY_CHARS",
    "OrderStatusData",
    "OrderStatusEvent",
    "ShipmentEventItem",
    "validate_idempotency_key",
]
