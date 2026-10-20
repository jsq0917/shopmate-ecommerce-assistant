"""Server-side idempotency primitives for write tools (contract §8).

The scope is ``(shop_id, actor_user_id, operation, idempotency_key)``. The database unique
constraint is the final arbiter; this module only describes the contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

OPERATION_CREATE_RETURN = "create_return_request"
OPERATION_CREATE_HANDOFF = "create_handoff_ticket"


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    """Write scope from contract §8.1."""

    shop_id: UUID
    actor_user_id: UUID
    operation: str
    key: str


@dataclass(frozen=True, slots=True)
class IdempotencyState:
    """Stored state of one idempotency key."""

    status: str
    request_hash: bytes
    resource_type: str | None = None
    resource_id: UUID | None = None
    response: Mapping[str, Any] | None = None
    error_code: str | None = None


class ClaimKind(StrEnum):
    """Outcome of trying to take ownership of an idempotency key."""

    CLAIMED = "claimed"
    REPLAY = "replay"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Result of :meth:`IdempotencyStore.claim`."""

    kind: ClaimKind
    state: IdempotencyState | None = None


class IdempotencyStore(Protocol):
    """Idempotency bookkeeping; a unique index makes concurrent claims safe."""

    async def claim(self, scope: IdempotencyScope, *, request_hash: bytes) -> ClaimResult:
        """Claim the key, or report the stored state when it already exists."""
        ...

    async def mark_succeeded(
        self,
        scope: IdempotencyScope,
        *,
        resource_type: str,
        resource_id: UUID,
        response: Mapping[str, Any],
    ) -> None:
        """Record the created resource and the replayable response."""
        ...

    async def mark_failed(self, scope: IdempotencyScope, *, error_code: str) -> None:
        """Record a terminal failure so a retry returns the same safe error."""
        ...

    async def release(self, scope: IdempotencyScope) -> None:
        """Release a claim that failed with a retryable error.

        Semantics: delete the record only while it is still ``processing``, so the same
        key can be claimed again. A ``succeeded`` record must never be deleted (that would
        drop a concurrent success result); deleting nothing is a silent no-op.
        """
        ...


__all__ = [
    "ClaimKind",
    "ClaimResult",
    "IdempotencyScope",
    "IdempotencyState",
    "IdempotencyStore",
    "OPERATION_CREATE_HANDOFF",
    "OPERATION_CREATE_RETURN",
]
