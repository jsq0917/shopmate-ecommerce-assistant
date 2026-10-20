"""Request identity middleware.

Sets a normalized ``request_id`` and a fresh ``trace_id`` on every request so the response
envelope and the exception handlers agree on the same correlation ids. A client-supplied
``X-Request-ID`` is honoured only when it is a valid UUID.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach ``request_id`` / ``trace_id`` to ``request.state``."""

    async def dispatch(self, request: Request, call_next):
        request_id = self._parse(request.headers.get("x-request-id")) or uuid4()
        request.state.request_id = request_id
        request.state.trace_id = uuid4()
        return await call_next(request)

    @staticmethod
    def _parse(value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value).strip())
        except ValueError:
            return None


__all__ = ["RequestIDMiddleware"]
