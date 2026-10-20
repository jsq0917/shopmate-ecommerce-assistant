"""Consumer-scoped reads for human handoff tickets.

A shopper may only ever see their own tickets. Both queries filter on ``shop_id`` and
``user_id`` together, so "not found" and "belongs to someone else" return the same
``None`` and the API emits one non-leaking 404 either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import HandoffTicket

EXPECTED_RESPONSE = "客服将优先查看；这不是退款或赔偿承诺。"


@dataclass(frozen=True, slots=True)
class HandoffTicketRow:
    """One ticket as rendered to the consumer API (no internal fields)."""

    id: UUID
    status: str
    risk_level: str
    primary_reason_code: str
    reason_codes: tuple[str, ...]
    priority: int
    queue: str
    summary_redacted: str
    expected_response: str
    created_at: datetime
    updated_at: datetime


def _queue(risk_level: str) -> str:
    return "priority_support" if risk_level in ("high", "critical") else "standard_support"


def _to_row(row: HandoffTicket) -> HandoffTicketRow:
    reason_codes = (
        list(row.risk_rule_codes_jsonb) if isinstance(row.risk_rule_codes_jsonb, list) else []
    )
    return HandoffTicketRow(
        id=row.id,
        status=str(row.status),
        risk_level=str(row.risk_level),
        primary_reason_code=row.primary_reason_code,
        reason_codes=tuple(str(code) for code in reason_codes),
        priority=row.priority,
        queue=_queue(str(row.risk_level)),
        summary_redacted=row.summary_redacted,
        expected_response=EXPECTED_RESPONSE,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class HandoffReadRepository:
    """Shop- and user-scoped ticket reads for the consumer handoff API."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self, *, shop_id: UUID, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[HandoffTicketRow, ...]:
        """Return the user's own tickets, newest first."""
        stmt = (
            sa.select(HandoffTicket)
            .where(HandoffTicket.shop_id == shop_id, HandoffTicket.user_id == user_id)
            .order_by(HandoffTicket.created_at.desc(), HandoffTicket.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(_to_row(row) for row in rows)

    async def get_for_user(
        self, *, shop_id: UUID, user_id: UUID, ticket_id: UUID
    ) -> HandoffTicketRow | None:
        """Return one of the user's own tickets, or ``None``."""
        stmt = sa.select(HandoffTicket).where(
            HandoffTicket.shop_id == shop_id,
            HandoffTicket.user_id == user_id,
            HandoffTicket.id == ticket_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_row(row)


__all__ = ["EXPECTED_RESPONSE", "HandoffReadRepository", "HandoffTicketRow"]
