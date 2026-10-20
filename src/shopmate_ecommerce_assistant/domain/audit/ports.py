"""Audit sink protocol used by the tool runtime."""

from __future__ import annotations

from typing import Protocol

from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord


class AuditSink(Protocol):
    """Receives already-redacted audit records."""

    async def record_tool_call(self, record: ToolCallRecord) -> None:
        """Persist one tool invocation."""
        ...

    async def record_event(self, event: AuditEventRecord) -> None:
        """Persist one security/business decision."""
        ...


class NullAuditSink:
    """No-op sink for unit tests and for read-only imports."""

    async def record_tool_call(self, record: ToolCallRecord) -> None:
        return None

    async def record_event(self, event: AuditEventRecord) -> None:
        return None


__all__ = ["AuditSink", "NullAuditSink"]
