"""Write-side contract for return applications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.idempotency import IdempotencyScope


@dataclass(frozen=True, slots=True)
class ReturnRequestRecord:
    """What the caller needs to render a submitted application."""

    id: UUID
    order_id: UUID
    order_item_id: UUID
    reason_code: str
    status: str
    submitted_at: datetime
    required_materials: tuple[str, ...]


class ReturnWriter(Protocol):
    """Creates one ``submitted`` application together with its audit rows."""

    async def create_submitted(
        self,
        *,
        return_request_id: UUID,
        shop_id: UUID,
        user_id: UUID,
        order_id: UUID,
        order_item_id: UUID,
        reason_code: str,
        required_materials: tuple[str, ...],
        tool_call: ToolCallRecord,
        audit: AuditEventRecord,
        scope: IdempotencyScope,
        response: Mapping[str, Any],
    ) -> ReturnRequestRecord:
        """Insert the application and commit; raise on any conflict."""
        ...


class ReturnConflictError(Exception):
    """Raised when the database already holds an active application for the item."""


__all__ = ["ReturnConflictError", "ReturnRequestRecord", "ReturnWriter"]
