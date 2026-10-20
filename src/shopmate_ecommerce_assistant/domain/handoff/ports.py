"""Write-side contract for human handoff tickets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.idempotency import IdempotencyScope


@dataclass(frozen=True, slots=True)
class HandoffTicketRecord:
    """What the caller needs to render an escalation."""

    id: UUID
    status: str
    risk_level: str
    priority: int
    primary_reason_code: str
    reason_codes: tuple[str, ...]
    created_at: datetime


class HandoffConflictError(Exception):
    """Raised when an audit/unique constraint already holds this logical write."""


class HandoffWriter(Protocol):
    """Creates one ``open`` ticket together with its audit rows."""

    async def create_open(
        self,
        *,
        ticket_id: UUID,
        shop_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        risk_level: str,
        primary_reason_code: str,
        reason_codes: tuple[str, ...],
        summary_redacted: str,
        priority: int,
        tool_call: ToolCallRecord,
        audit: AuditEventRecord,
        scope: IdempotencyScope,
        response: Mapping[str, Any],
    ) -> HandoffTicketRecord:
        """Insert the ticket and commit; raise on any conflict."""
        ...


__all__ = ["HandoffConflictError", "HandoffTicketRecord", "HandoffWriter"]
