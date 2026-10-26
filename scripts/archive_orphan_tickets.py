"""Archive support tickets whose conversation no longer exists.

Why this exists
---------------
The stage-13 evaluation harness soft-deletes the conversations it creates, but the handoff
tickets those runs raised stayed ``open`` forever. The workbench then showed rows an agent
could never open ("未找到该会话。"). This script archives them through the normal state
machine (``open|assigned|resolved -> closed``) with an audit event per ticket, so nothing is
hard-deleted and every move stays explainable.

Usage
-----
    uv run python scripts/archive_orphan_tickets.py            # dry run, prints the plan
    uv run python scripts/archive_orphan_tickets.py --apply     # actually archive

Options
-------
    --reason TEXT   archive reason recorded on every ticket (default: see DEFAULT_REASON)
    --limit N       stop after N tickets (safety valve)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.db.models import Conversation, HandoffTicket, User, UserRole
from shopmate_ecommerce_assistant.db.repositories.audit import AuditRepository
from shopmate_ecommerce_assistant.db.repositories.support import (
    InvalidTicketTransition,
    SupportRepository,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord

DEFAULT_REASON = "关联会话已不存在（评测/清理残留），历史工单归档"


async def _actor_for(session: object, shop_id: UUID) -> UUID | None:
    """Pick a support agent of the shop to stand in as the actor (keeps audit meaningful)."""
    result = await session.execute(  # type: ignore[attr-defined]
        sa.select(User.id)
        .where(User.shop_id == shop_id, User.role == UserRole.SUPPORT)
        .order_by(User.created_at, User.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _orphan_tickets(session: object) -> list[tuple[UUID, UUID, str]]:
    """Return ``(shop_id, ticket_id, status)`` for tickets with a gone conversation."""
    live = (
        sa.select(Conversation.id)
        .where(
            Conversation.shop_id == HandoffTicket.shop_id,
            Conversation.id == HandoffTicket.conversation_id,
            Conversation.deleted_at.is_(None),
        )
        .correlate(HandoffTicket)
        .exists()
    )
    result = await session.execute(  # type: ignore[attr-defined]
        sa.select(HandoffTicket.shop_id, HandoffTicket.id, HandoffTicket.status)
        .where(HandoffTicket.status != "closed", sa.not_(live))
        .order_by(HandoffTicket.created_at, HandoffTicket.id)
    )
    return [(row[0], row[1], str(row[2])) for row in result.all()]


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写库；不带则只打印计划")
    parser.add_argument("--reason", default=DEFAULT_REASON)
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0 = 不限）")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            orphans = await _orphan_tickets(session)
            if args.limit:
                orphans = orphans[: args.limit]
            print(f"发现待归档工单：{len(orphans)} 条（status != closed 且会话已删除/缺失）")
            by_status: dict[str, int] = {}
            for _, _, status in orphans:
                by_status[status] = by_status.get(status, 0) + 1
            print(f"  状态分布：{by_status or '{}'}")
            if not orphans:
                return 0
            if not args.apply:
                print("\n这是 dry run。加 --apply 才会写库。")
                return 0

            support = SupportRepository(session)
            audit = AuditRepository(session)
            archived = 0
            actors: dict[UUID, UUID | None] = {}
            for shop_id, ticket_id, status in orphans:
                if shop_id not in actors:
                    actors[shop_id] = await _actor_for(session, shop_id)
                actor = actors[shop_id]
                if actor is None:
                    print(f"  跳过 {ticket_id}：该店铺没有 support 账号，无法留痕")
                    continue
                try:
                    await support.transition(
                        shop_id=shop_id,
                        ticket_id=ticket_id,
                        actor_user_id=actor,
                        action="archive",
                        close_reason=args.reason,
                    )
                except InvalidTicketTransition as exc:
                    print(f"  跳过 {ticket_id}（{status}）：{exc}")
                    continue
                await audit.record_event(
                    AuditEventRecord(
                        id=uuid4(),
                        shop_id=shop_id,
                        actor_user_id=actor,
                        actor_role=UserRole.SUPPORT.value,
                        action="support.ticket.archive",
                        resource_type="handoff_ticket",
                        resource_id=ticket_id,
                        request_id=uuid4(),
                        trace_id=uuid4(),
                        outcome="succeeded",
                        metadata={"from_status": status, "reason": args.reason, "source": "script"},
                    )
                )
                archived += 1
            finished = datetime.now(UTC).isoformat()
            print(f"\n已归档 {archived} 条，写入审计事件 {archived} 条，完成于 {finished}")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
