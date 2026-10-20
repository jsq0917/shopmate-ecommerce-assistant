"""Unified JSON response envelope (docs/06-api.md section 3).

Success, list and error responses all share ``request_id`` + ``trace_id`` so a client and a
support agent can correlate a turn across services without leaking internals.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    """``{data, request_id, trace_id}`` for both single items and list payloads.

    List endpoints put a concrete ``*ListData`` model (``items`` + pagination token) into
    ``data``, e.g. ``Envelope[MessageListData]``.
    """

    data: T
    request_id: UUID
    trace_id: UUID


class ErrorBody(BaseModel):
    """``{code, message, retryable, retry_after_ms, details}``."""

    code: str
    message: str
    retryable: bool = False
    retry_after_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """``{error, request_id, trace_id}``."""

    error: ErrorBody
    request_id: UUID
    trace_id: UUID


__all__ = ["Envelope", "ErrorBody", "ErrorEnvelope"]
