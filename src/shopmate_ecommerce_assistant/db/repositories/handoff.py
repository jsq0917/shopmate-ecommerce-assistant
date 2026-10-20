"""Writes for human handoff tickets.

Like the return writer, everything is committed in one transaction: the ticket, the
``tool_calls`` row, the ``audit_events`` row and the idempotency completion. The ticket is
always ``open``; assignment and resolution belong to the support desk, not to a chat tool.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import AuditEvent as AuditEventModel
from shopmate_ecommerce_assistant.db.models import (
    HandoffStatus,
    HandoffTicket,
    IdempotencyRecord,
    IdempotencyStatus,
    ToolCall,
)
from shopmate_ecommerce_assistant.db.repositories.audit import (
    audit_event_values,
    tool_call_values,
)
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.handoff.ports import (
    HandoffConflictError,
    HandoffTicketRecord,
)
from shopmate_ecommerce_assistant.domain.idempotency import IdempotencyScope
from shopmate_ecommerce_assistant.safety.risk import RiskLevel


class HandoffRepository:
    """SQLAlchemy implementation of :class:`HandoffWriter`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        """Insert the ticket, audit rows and idempotency completion atomically."""
        now = datetime.now(UTC)
        row = HandoffTicket(
            id=ticket_id,
            shop_id=shop_id,
            conversation_id=conversation_id,
            user_id=user_id,
            risk_level=RiskLevel(risk_level),
            primary_reason_code=primary_reason_code,
            risk_rule_codes_jsonb=list(reason_codes),
            summary_redacted=summary_redacted,
            status=HandoffStatus.OPEN,
            priority=priority,
            idempotency_key=scope.key,
            is_synthetic=True,
        )
        self._session.add(row)
        try:
            await self._session.flush()
            await self._session.execute(sa.insert(ToolCall).values(**tool_call_values(tool_call)))
            await self._session.execute(
                sa.insert(AuditEventModel).values(**audit_event_values(audit, occurred_at=now))
            )
            completed = await self._session.execute(
                sa.update(IdempotencyRecord)
                .where(
                    IdempotencyRecord.shop_id == scope.shop_id,
                    IdempotencyRecord.actor_user_id == scope.actor_user_id,
                    IdempotencyRecord.operation == scope.operation,
                    IdempotencyRecord.idempotency_key == scope.key,
                )
                .values(
                    status=IdempotencyStatus.SUCCEEDED,
                    resource_type="handoff_ticket",
                    resource_id=ticket_id,
                    response_snapshot_jsonb=dict(response),
                    updated_at=sa.func.now(),
                )
            )
            if completed.rowcount != 1:
                raise RuntimeError("idempotency scope disappeared mid-transaction")
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HandoffConflictError("duplicate handoff write") from exc
        except Exception:
            await self._session.rollback()
            raise

        return HandoffTicketRecord(
            id=ticket_id,
            status=HandoffStatus.OPEN.value,
            risk_level=risk_level,
            priority=priority,
            primary_reason_code=primary_reason_code,
            reason_codes=tuple(reason_codes),
            created_at=now,
        )


__all__ = ["HandoffRepository"]
