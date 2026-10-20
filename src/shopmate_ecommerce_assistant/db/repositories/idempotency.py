"""PostgreSQL-backed idempotency bookkeeping.

The unique constraint ``uq_idempotency_scope`` is the arbiter: two concurrent requests with
the same key can never both create a resource, and ``ON CONFLICT DO NOTHING`` tells the
loser to read the winner's state instead of failing.

A record left in ``processing`` (crash between claim and write) is taken over after
``STALE_AFTER_SECONDS`` so a transient failure cannot block the key forever. Until then the
caller gets ``IDEMPOTENCY_IN_PROGRESS``, which the contract marks retryable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import IdempotencyRecord, IdempotencyStatus
from shopmate_ecommerce_assistant.domain.idempotency import (
    ClaimKind,
    ClaimResult,
    IdempotencyScope,
    IdempotencyState,
)

STALE_AFTER_SECONDS = 120
RETENTION_DAYS = 7


class IdempotencyRepository:
    """SQLAlchemy implementation of :class:`IdempotencyStore`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, scope: IdempotencyScope, *, request_hash: bytes) -> ClaimResult:
        """Claim the key or report the stored state."""
        now = datetime.now(UTC)
        row = await self._load(scope)
        if row is None:
            stmt = (
                pg_insert(IdempotencyRecord)
                .values(
                    id=uuid4(),
                    shop_id=scope.shop_id,
                    actor_user_id=scope.actor_user_id,
                    operation=scope.operation,
                    idempotency_key=scope.key,
                    request_hash=request_hash,
                    status=IdempotencyStatus.PROCESSING,
                    expires_at=now + timedelta(days=RETENTION_DAYS),
                )
                .on_conflict_do_nothing(constraint="uq_idempotency_scope")
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            if result.rowcount:
                return ClaimResult(ClaimKind.CLAIMED)
            row = await self._load(scope)
            if row is None:
                return ClaimResult(ClaimKind.IN_PROGRESS)

        if bytes(row.request_hash) != request_hash:
            return ClaimResult(ClaimKind.CONFLICT, _state(row))
        if row.status is IdempotencyStatus.SUCCEEDED:
            return ClaimResult(ClaimKind.REPLAY, _state(row))
        if row.status is IdempotencyStatus.FAILED:
            return ClaimResult(ClaimKind.FAILED, _state(row))

        stale_before = now - timedelta(seconds=STALE_AFTER_SECONDS)
        if row.updated_at <= stale_before:
            takeover = (
                sa.update(IdempotencyRecord)
                .where(
                    IdempotencyRecord.id == row.id,
                    IdempotencyRecord.status == IdempotencyStatus.PROCESSING,
                    IdempotencyRecord.updated_at <= stale_before,
                )
                .values(updated_at=sa.func.now())
                .returning(IdempotencyRecord.id)
            )
            taken = (await self._session.execute(takeover)).scalar_one_or_none()
            await self._session.commit()
            if taken is not None:
                return ClaimResult(ClaimKind.CLAIMED)
        return ClaimResult(ClaimKind.IN_PROGRESS, _state(row))

    async def mark_succeeded(
        self,
        scope: IdempotencyScope,
        *,
        resource_type: str,
        resource_id: UUID,
        response: Mapping[str, Any],
    ) -> None:
        """Record the created resource and the replayable response, then commit."""
        await self._update(
            scope,
            {
                "status": IdempotencyStatus.SUCCEEDED,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "response_snapshot_jsonb": dict(response),
                "updated_at": sa.func.now(),
            },
        )

    async def mark_failed(self, scope: IdempotencyScope, *, error_code: str) -> None:
        """Record a terminal failure so a same-key retry returns the same safe error."""
        await self._update(
            scope,
            {
                "status": IdempotencyStatus.FAILED,
                "response_snapshot_jsonb": {"error_code": error_code},
                "updated_at": sa.func.now(),
            },
        )

    async def release(self, scope: IdempotencyScope) -> None:
        """Delete the key only while it is still ``processing`` (contract §8.3).

        A retryable failure must not leave a terminal ``failed`` row that would poison the
        key forever. The conditional ``DELETE ... WHERE status = 'processing'`` leaves a
        ``succeeded`` record untouched, so a concurrent success can never be dropped; when
        nothing matches (``rowcount == 0``) the release is silently a no-op.
        """
        stmt = sa.delete(IdempotencyRecord).where(
            IdempotencyRecord.shop_id == scope.shop_id,
            IdempotencyRecord.actor_user_id == scope.actor_user_id,
            IdempotencyRecord.operation == scope.operation,
            IdempotencyRecord.idempotency_key == scope.key,
            IdempotencyRecord.status == IdempotencyStatus.PROCESSING,
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def _update(self, scope: IdempotencyScope, values: dict[str, Any]) -> None:
        stmt = (
            sa.update(IdempotencyRecord)
            .where(
                IdempotencyRecord.shop_id == scope.shop_id,
                IdempotencyRecord.actor_user_id == scope.actor_user_id,
                IdempotencyRecord.operation == scope.operation,
                IdempotencyRecord.idempotency_key == scope.key,
            )
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def _load(self, scope: IdempotencyScope) -> IdempotencyRecord | None:
        stmt = sa.select(IdempotencyRecord).where(
            IdempotencyRecord.shop_id == scope.shop_id,
            IdempotencyRecord.actor_user_id == scope.actor_user_id,
            IdempotencyRecord.operation == scope.operation,
            IdempotencyRecord.idempotency_key == scope.key,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()


def _state(row: IdempotencyRecord) -> IdempotencyState:
    response = (
        row.response_snapshot_jsonb if isinstance(row.response_snapshot_jsonb, dict) else None
    )
    return IdempotencyState(
        status=str(row.status),
        request_hash=bytes(row.request_hash),
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        response=response,
        error_code=None if response is None else response.get("error_code"),
    )


__all__ = ["IdempotencyRepository", "RETENTION_DAYS", "STALE_AFTER_SECONDS"]
