"""Audit records shared by the tool runtime and the repositories.

These are plain data: no ORM, no request objects. Both records are already redacted when
they are built — the repository never inspects raw user text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """One row of ``tool_calls``: what ran, for whom, how long, and the outcome."""

    id: UUID
    request_id: UUID
    trace_id: UUID
    shop_id: UUID
    conversation_id: UUID | None
    user_id: UUID
    actor_user_id: UUID
    tool_name: str
    input_redacted: dict[str, Any]
    result_summary: dict[str, Any]
    status: str
    error_code: str | None
    latency_ms: int
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class AuditEventRecord:
    """One row of ``audit_events``: a permission, idempotency or escalation decision."""

    id: UUID
    shop_id: UUID
    actor_user_id: UUID | None
    actor_role: str | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    request_id: UUID | None
    trace_id: UUID | None
    outcome: str
    metadata: dict[str, Any]
    risk_level: str | None = None


__all__ = ["AuditEventRecord", "ToolCallRecord"]
