"""Stable, user-safe error types for tool boundaries.

Tools never let SQLAlchemy or Pydantic exceptions reach the caller or the model.
Every failure is mapped to one of the codes below plus a Chinese, actionable message
that contains no SQL, stack trace, connection string or PII.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Error codes registered in ``docs/05-tool-contract.md`` section 4."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    FORBIDDEN = "FORBIDDEN"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    VARIANT_NOT_FOUND = "VARIANT_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    SHIPMENT_NOT_FOUND = "SHIPMENT_NOT_FOUND"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    INVALID_STATE = "INVALID_STATE"
    RETURN_NOT_ALLOWED = "RETURN_NOT_ALLOWED"
    RETURN_WINDOW_EXPIRED = "RETURN_WINDOW_EXPIRED"
    DUPLICATE_RETURN = "DUPLICATE_RETURN"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    ELIGIBILITY_EXPIRED = "ELIGIBILITY_EXPIRED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
    TOOL_BUDGET_EXCEEDED = "TOOL_BUDGET_EXCEEDED"
    RISK_HANDOFF_REQUIRED = "RISK_HANDOFF_REQUIRED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Error codes the contract (``docs/05-tool-contract.md`` §4) marks retryable.
#:
#: A write tool must *release* its idempotency claim for these instead of marking it a
#: terminal ``failed``, so a same-key retry can succeed once the transient cause
#: (missing confirmation, low confidence, an upstream blip) is resolved. ``INTERNAL_ERROR``
#: is "视情况" per the contract and is handled separately in the write path.
RETRYABLE_ERROR_CODES = frozenset(
    {
        "OUT_OF_STOCK",
        "LOW_CONFIDENCE",
        "CONFIRMATION_REQUIRED",
        "ELIGIBILITY_EXPIRED",
        "IDEMPOTENCY_IN_PROGRESS",
        "UPSTREAM_UNAVAILABLE",
        "RATE_LIMITED",
    }
)


class ToolError(Exception):
    """A controlled tool failure carrying a stable code and a safe user message."""

    def __init__(
        self,
        code: ErrorCode,
        user_message: str,
        *,
        retryable: bool = False,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
