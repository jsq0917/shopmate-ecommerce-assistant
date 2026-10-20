"""Audit persistence for tool calls and security/business events.

The repository only accepts already-redacted records; it never sees raw payloads. Both
writers commit on their own because a read tool has no larger transaction to join.

A duplicate ``tool_calls`` insert can only mean the same idempotent write is being audited
twice; the unique index rejects it and the writer rolls back instead of failing the call.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import AuditEvent, ToolCall
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.safety.risk import RiskLevel

logger = logging.getLogger(__name__)


def tool_call_values(record: ToolCallRecord) -> dict[str, Any]:
    """Return the insert values for one ``tool_calls`` row."""
    return {
        "id": record.id,
        "request_id": record.request_id,
        "trace_id": record.trace_id,
        "shop_id": record.shop_id,
        "conversation_id": record.conversation_id,
        "user_id": record.user_id,
        "actor_user_id": record.actor_user_id,
        "tool_name": record.tool_name,
        "input_redacted_jsonb": dict(record.input_redacted),
        "result_summary_jsonb": dict(record.result_summary),
        "status": record.status,
        "error_code": record.error_code,
        "latency_ms": max(0, record.latency_ms),
        "idempotency_key": record.idempotency_key,
    }


def audit_event_values(event: AuditEventRecord, *, occurred_at: datetime) -> dict[str, Any]:
    """Return the insert values for one ``audit_events`` row."""
    return {
        "id": event.id,
        "shop_id": event.shop_id,
        "actor_user_id": event.actor_user_id,
        "actor_role": event.actor_role,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "request_id": event.request_id,
        "trace_id": event.trace_id,
        "outcome": event.outcome,
        "risk_level": None if event.risk_level is None else RiskLevel(event.risk_level),
        "metadata_redacted_jsonb": dict(event.metadata),
        "occurred_at": occurred_at,
    }


class AuditRepository:
    """SQLAlchemy implementation of :class:`AuditSink`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_tool_call(self, record: ToolCallRecord) -> None:
        """Insert one ``tool_calls`` row and commit."""
        self._session.add(ToolCall(**tool_call_values(record)))
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            logger.info("tool call %s already audited", record.tool_name)

    async def record_event(self, event: AuditEventRecord) -> None:
        """Insert one ``audit_events`` row and commit."""
        self._session.add(AuditEvent(**audit_event_values(event, occurred_at=datetime.now(UTC))))
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            logger.info("audit event %s already recorded", event.action)


__all__ = ["AuditRepository", "audit_event_values", "tool_call_values"]
