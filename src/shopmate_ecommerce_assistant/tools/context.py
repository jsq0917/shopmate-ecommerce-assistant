"""Injected tool execution context.

Identity and tenant scope never come from the model or the request payload: the backend
fills this context from the authenticated request and passes it in explicitly.

Stage 9 adds six server-owned pieces to that contract:

* ``conversation_id`` — the conversation a write tool may act inside;
* ``risk_context`` — the risk level and rule codes assessed by the router;
* ``confirmation`` — a one-time grant proving the user explicitly confirmed a write;
* ``route_confidence`` — the router's confidence, so a write tool can refuse when unsure;
* ``clarification_attempted`` — whether the router already asked once for clarification;
* ``idempotency_key`` — the API ``Idempotency-Key`` header or a server-side operation id.

A model cannot set, raise or lower any of them: they are dataclass fields filled by the
service layer, and the tool input schemas forbid unknown fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.safety.risk import RiskLevel

CATALOG_READ_ROLES = frozenset({UserRole.SHOPPER, UserRole.SUPPORT, UserRole.ADMIN})

#: Permission that lets support/admin read a consumer's data through an authorized
#: conversation or ticket. Without it, a non-shopper context has no order access at all.
SUPPORT_SCOPE_PERMISSION = "support:conversation:read"

ORDER_FORBIDDEN_MESSAGE = "当前账号无权查看该订单。请使用本人账号登录，或转人工协助。"
RETURN_WRITE_FORBIDDEN_MESSAGE = "退货申请只能由本人在确认后提交。如需协助，请转人工。"
CONVERSATION_FORBIDDEN_MESSAGE = "当前账号无权在该会话中操作。请确认会话归属，或转人工协助。"


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Risk level and rule codes produced by the router or the safety guards."""

    level: RiskLevel = RiskLevel.LOW
    codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfirmationGrant:
    """Server-issued proof that the user confirmed one specific write.

    ``covers`` re-checks the operation and the resource, so a grant for one order item
    cannot authorize a different one, and an expired grant cannot authorize anything.
    """

    operation: str
    order_id: UUID | None = None
    order_item_id: UUID | None = None
    reason_code: str | None = None
    expires_at: datetime | None = None

    def covers(
        self,
        *,
        operation: str,
        now: datetime,
        order_id: UUID | None = None,
        order_item_id: UUID | None = None,
        reason_code: str | None = None,
    ) -> bool:
        """Return True only for the exact operation/resource this grant was issued for."""
        if self.operation != operation:
            return False
        if self.expires_at is not None and now > self.expires_at:
            return False
        if self.order_id is not None and self.order_id != order_id:
            return False
        if self.order_item_id is not None and self.order_item_id != order_item_id:
            return False
        if self.reason_code is not None and self.reason_code != reason_code:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Immutable, server-side identity for one tool invocation."""

    shop_id: UUID
    actor_user_id: UUID
    role: UserRole
    request_id: UUID
    trace_id: UUID
    effective_user_id: UUID | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    conversation_id: UUID | None = None
    risk_context: RiskContext | None = None
    confirmation: ConfirmationGrant | None = None
    route_confidence: float | None = None
    clarification_attempted: bool = False
    idempotency_key: str | None = None

    @property
    def subject_user_id(self) -> UUID:
        """The user whose data is being read (equals the actor for shoppers)."""
        return self.effective_user_id or self.actor_user_id

    def ensure_catalog_read(self) -> None:
        """Reject roles that may not read the store catalog."""
        if self.role not in CATALOG_READ_ROLES:
            raise ToolError(
                ErrorCode.FORBIDDEN,
                "当前账号无权查看商品信息。请登录后再试，或转人工协助。",
            )

    def ensure_order_read(self) -> None:
        """Allow self-service shoppers, or support/admin with an authorized scope.

        A shopper with a *different* effective user is rejected: that combination can only
        come from a payload-supplied identity, which must never be honoured.
        """
        if self.effective_user_id is None or self.effective_user_id == self.actor_user_id:
            if self.role is UserRole.SHOPPER:
                return
            raise ToolError(ErrorCode.FORBIDDEN, ORDER_FORBIDDEN_MESSAGE)
        if self.role in (UserRole.SUPPORT, UserRole.ADMIN) and (
            SUPPORT_SCOPE_PERMISSION in self.permissions
        ):
            return
        raise ToolError(ErrorCode.FORBIDDEN, ORDER_FORBIDDEN_MESSAGE)

    def ensure_return_write(self) -> None:
        """Only the shopper acting for themselves may submit a return application."""
        if self.role is not UserRole.SHOPPER or self.subject_user_id != self.actor_user_id:
            raise ToolError(ErrorCode.FORBIDDEN, RETURN_WRITE_FORBIDDEN_MESSAGE)

    def ensure_conversation_read(self) -> None:
        """Reject contexts that may not act inside a conversation at all."""
        if self.effective_user_id is None or self.effective_user_id == self.actor_user_id:
            if self.role is UserRole.SHOPPER:
                return
            raise ToolError(ErrorCode.FORBIDDEN, CONVERSATION_FORBIDDEN_MESSAGE)
        if self.role in (UserRole.SUPPORT, UserRole.ADMIN) and (
            SUPPORT_SCOPE_PERMISSION in self.permissions
        ):
            return
        raise ToolError(ErrorCode.FORBIDDEN, CONVERSATION_FORBIDDEN_MESSAGE)


__all__ = [
    "CATALOG_READ_ROLES",
    "CONVERSATION_FORBIDDEN_MESSAGE",
    "ConfirmationGrant",
    "ORDER_FORBIDDEN_MESSAGE",
    "RETURN_WRITE_FORBIDDEN_MESSAGE",
    "RiskContext",
    "SUPPORT_SCOPE_PERMISSION",
    "ToolContext",
]
