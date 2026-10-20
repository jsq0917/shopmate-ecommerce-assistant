"""One audited execution path for every tool call.

Handlers only contain business logic. The runtime owns what must never be skipped:

* mapping any exception to a stable error code with a Chinese, actionable message;
* never returning SQL, a stack trace, a connection string or PII to the model;
* writing exactly one ``tool_calls`` row per logical call, with the same ``tool_call_id``
  that the envelope carries, the redacted input, a minimal result summary and the latency.

An idempotent replay passes ``audit=False``: the contract requires the original
``tool_call_id`` and forbids a second audit row for the same logical write.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.domain.audit.models import ToolCallRecord
from shopmate_ecommerce_assistant.domain.audit.ports import AuditSink, NullAuditSink
from shopmate_ecommerce_assistant.tools.audit import redact_tool_input, summarize_result
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure, ToolResult

logger = logging.getLogger(__name__)

UPSTREAM_MESSAGE = "订单或物流数据暂时无法读取，请稍后重试；如持续失败可转人工协助。"
INTERNAL_MESSAGE = "本次操作出现异常，请稍后重试或转人工协助。"


def utc_now() -> datetime:
    """Return the current UTC instant (injectable for deterministic tests)."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """A handler's result plus whether this call deserves an audit row."""

    result: ToolResult
    audit: bool = True


ToolHandler = Callable[[Any, ToolContext], Awaitable[ToolOutcome]]


class ToolRuntime:
    """Executes handlers with stable error mapping and tool-call auditing."""

    def __init__(self, audit: AuditSink | None = None) -> None:
        self._audit: AuditSink = audit or NullAuditSink()

    async def execute(
        self,
        tool_name: str,
        *,
        context: ToolContext,
        payload: Any,
        handler: ToolHandler,
    ) -> ToolResult:
        """Run one handler and return its envelope, auditing the call."""
        started = time.perf_counter()
        should_audit = True
        try:
            outcome = await handler(payload, context)
        except ToolError as exc:
            result: ToolResult = ToolFailure(
                tool_call_id=uuid4(),
                error_code=exc.code.value,
                user_message=exc.user_message,
                retryable=exc.retryable,
                retry_after_ms=exc.retry_after_ms,
                trace_id=context.trace_id,
            )
        except SQLAlchemyError:
            logger.warning("tool %s failed: database unavailable", tool_name)
            result = ToolFailure(
                tool_call_id=uuid4(),
                error_code=ErrorCode.UPSTREAM_UNAVAILABLE.value,
                user_message=UPSTREAM_MESSAGE,
                retryable=True,
                trace_id=context.trace_id,
            )
        except Exception:
            # Deliberately no exc_info: an unexpected message can echo user input or SQL.
            logger.error("tool %s failed: unexpected error", tool_name)
            result = ToolFailure(
                tool_call_id=uuid4(),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                user_message=INTERNAL_MESSAGE,
                trace_id=context.trace_id,
            )
        else:
            result = outcome.result
            should_audit = outcome.audit

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        if should_audit:
            await self._record(tool_name, context, payload, result, latency_ms)
        return result

    async def _record(
        self,
        tool_name: str,
        context: ToolContext,
        payload: Any,
        result: ToolResult,
        latency_ms: int,
    ) -> None:
        key = self._idempotency_key(context, payload)
        record = ToolCallRecord(
            id=result.tool_call_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            shop_id=context.shop_id,
            conversation_id=context.conversation_id,
            user_id=context.subject_user_id,
            actor_user_id=context.actor_user_id,
            tool_name=tool_name,
            input_redacted=redact_tool_input(tool_name, payload, idempotency_key=key),
            result_summary=summarize_result(tool_name, result),
            status="succeeded" if result.ok else "failed",
            error_code=None if result.ok else result.error_code,
            latency_ms=latency_ms,
            idempotency_key=key,
        )
        try:
            await self._audit.record_tool_call(record)
        except Exception:
            # Losing the audit row must not turn a successful read into a failure, and the
            # repository has already logged the safe reason.
            logger.warning("tool audit write failed for %s", tool_name)

    @staticmethod
    def _idempotency_key(context: ToolContext, payload: Any) -> str | None:
        # The write tools get their key from the server-injected context, not the payload.
        if context.idempotency_key:
            return context.idempotency_key
        # Backward-compatible fallback for callers that still pass the key in the payload.
        if isinstance(payload, dict):
            key = payload.get("idempotency_key")
            if isinstance(key, str) and key:
                return key
        key = getattr(payload, "idempotency_key", None)
        return key if isinstance(key, str) and key else None


def tool_call_id_of(result: ToolResult) -> UUID:
    """Return the envelope's ``tool_call_id`` (used by tests and callers)."""
    return result.tool_call_id


__all__ = ["ToolOutcome", "ToolRuntime", "tool_call_id_of", "utc_now"]
