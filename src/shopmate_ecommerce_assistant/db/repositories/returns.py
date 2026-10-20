"""Writes for return applications.

One method, one transaction: the application row, the ``tool_calls`` audit row, the
``audit_events`` row and the idempotency completion are committed together. If any of them
fails, nothing is written — a retry can then safely reuse the same key.

The partial unique index ``uq_return_active_item`` is what prevents two active applications
for one order item; it is translated into :class:`ReturnConflictError`, never into a
database error the model could see.
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
    IdempotencyRecord,
    IdempotencyStatus,
    ReturnRequest,
    ReturnStatus,
    ToolCall,
)
from shopmate_ecommerce_assistant.db.repositories.audit import (
    audit_event_values,
    tool_call_values,
)
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.idempotency import IdempotencyScope
from shopmate_ecommerce_assistant.domain.returns.ports import (
    ReturnConflictError,
    ReturnRequestRecord,
)

_CONFLICT_CONSTRAINTS = ("uq_return_active_item", "uq_tool_calls_idempotency")


def _is_conflict(exc: IntegrityError) -> bool:
    text = str(getattr(exc, "orig", exc))
    return any(name in text for name in _CONFLICT_CONSTRAINTS)


class ReturnRepository:
    """SQLAlchemy implementation of :class:`ReturnWriter`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        """Insert the application, audit rows and idempotency completion atomically."""
        now = datetime.now(UTC)
        row = ReturnRequest(
            id=return_request_id,
            shop_id=shop_id,
            user_id=user_id,
            order_id=order_id,
            order_item_id=order_item_id,
            reason_code=reason_code,
            status=ReturnStatus.SUBMITTED,
            requested_at=now,
            submitted_at=now,
            required_materials_jsonb=list(required_materials),
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
                    resource_type="return_request",
                    resource_id=return_request_id,
                    response_snapshot_jsonb=dict(response),
                    updated_at=sa.func.now(),
                )
            )
            if completed.rowcount != 1:
                raise RuntimeError("idempotency scope disappeared mid-transaction")
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_conflict(exc):
                raise ReturnConflictError("active return exists") from exc
            raise
        except Exception:
            await self._session.rollback()
            raise

        return ReturnRequestRecord(
            id=return_request_id,
            order_id=order_id,
            order_item_id=order_item_id,
            reason_code=reason_code,
            status=ReturnStatus.SUBMITTED.value,
            submitted_at=now,
            required_materials=tuple(required_materials),
        )


__all__ = ["ReturnRepository"]
