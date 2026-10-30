"""Support workbench repository: queue, detail, state machine and quality labels.

Everything here is shop-scoped. A ticket, a conversation and an assistant message can
only be reached through a row that carries the caller's ``shop_id``, so a support agent
of one tenant can never observe another tenant's queue. Agent-facing reads deliberately
return *masked* references and safe summaries: no full e-mail, address, order recipient,
system prompt or internal stack ever leaves this layer.

The state machine is enforced here rather than in the router because the same rules must
hold for any future caller (CLI, worker, test). Illegal transitions raise
:class:`InvalidTicketTransition`, which the API maps to ``409 INVALID_STATE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    Conversation,
    HandoffStatus,
    HandoffTicket,
    Message,
    SupportQualityLabel,
    ToolCall,
    User,
    UserRole,
)
from shopmate_ecommerce_assistant.db.repositories.handoff_read import EXPECTED_RESPONSE
from shopmate_ecommerce_assistant.safety.pii import mask_pii

#: ``action`` -> (allowed current statuses, target status).
#:
#: ``archive`` exists because a ticket can outlive its transcript: the stage-13 evaluation
#: harness soft-deletes the conversations it creates, and any ticket those runs raised used
#: to stay ``open`` forever, flooding the workbench with rows an agent could never open.
#: Archiving is a terminal, audited move (never a hard delete) and requires a reason.
TRANSITIONS: dict[str, tuple[frozenset[HandoffStatus], HandoffStatus]] = {
    "assign": (frozenset({HandoffStatus.OPEN, HandoffStatus.ASSIGNED}), HandoffStatus.ASSIGNED),
    "resolve": (frozenset({HandoffStatus.ASSIGNED}), HandoffStatus.RESOLVED),
    "close": (frozenset({HandoffStatus.RESOLVED}), HandoffStatus.CLOSED),
    "archive": (
        frozenset({HandoffStatus.OPEN, HandoffStatus.ASSIGNED, HandoffStatus.RESOLVED}),
        HandoffStatus.CLOSED,
    ),
}

ELEVATED_ROLES = (UserRole.SUPPORT, UserRole.ADMIN)


class InvalidTicketTransition(Exception):
    """The requested status change is not allowed from the ticket's current state."""


class UnknownAssignee(Exception):
    """The requested assignee does not exist in this shop or cannot handle tickets."""


class TicketNotTakenOver(Exception):
    """The caller never claimed this ticket, so it has no right to write into the case."""


def ensure_reply_allowed(ticket: SupportTicketRow, *, agent_user_id: UUID) -> None:
    """Raise unless ``agent_user_id`` may append a human reply to this ticket.

    Reading a transcript is deliberately *not* gated: an agent has to read the case before
    deciding whether to take it. Writing into the shopper's conversation is gated, because
    an unclaimed ticket would otherwise let any account holding ``support:ticket:write``
    answer the shopper without going through the ``接管`` handshake.
    """
    status = str(ticket.status)
    if status == HandoffStatus.OPEN.value:
        raise TicketNotTakenOver("工单尚未接管，不能回复用户；请先点击「接管」。")
    if status == HandoffStatus.RESOLVED.value:
        raise TicketNotTakenOver("工单已标记解决，不能再回复用户。")
    if status == HandoffStatus.CLOSED.value:
        raise TicketNotTakenOver("工单已关闭，不能再回复用户。")
    if ticket.assigned_to != agent_user_id:
        raise TicketNotTakenOver("该工单已由其他客服接管，不能回复用户；如需回复请先接管。")


def ensure_ticket_owned(
    ticket: SupportTicketRow, *, agent_user_id: UUID, action: str
) -> None:
    """Raise unless ``agent_user_id`` is the agent currently holding this ticket."""
    if ticket.assigned_to is None:
        raise TicketNotTakenOver(f"工单尚未接管，不能{action}；请先点击「接管」。")
    if ticket.assigned_to != agent_user_id:
        raise TicketNotTakenOver(f"该工单已由其他客服接管，不能{action}；如需继续处理请先接管。")


def queue_for(risk_level: str) -> str:
    """Return the stable queue name for a risk level (contract §12)."""
    return "priority_support" if risk_level in ("high", "critical") else "standard_support"


def mask_reference(user_id: UUID | None, display_name_masked: str | None) -> str | None:
    """Return a non-PII reference for a user id.

    ``users.display_name_masked`` is already masked at registration time; when it is
    absent (synthetic rows) the last two id characters keep the value stable and
    correlatable across a queue view without exposing anything identifying.
    """
    if user_id is None:
        return None
    if display_name_masked:
        return display_name_masked
    return f"user-****{str(user_id)[-2:]}"


@dataclass(frozen=True, slots=True)
class SupportTicketRow:
    """One queue/list item (contract §12 固定字段)."""

    ticket_id: UUID
    status: str
    risk_level: str
    primary_reason_code: str
    reason_codes: tuple[str, ...]
    priority: int
    queue: str
    conversation_id: UUID
    user_reference_masked: str
    assigned_to_masked: str | None
    created_at: datetime
    updated_at: datetime
    waiting_seconds: int
    summary_redacted: str
    expected_response: str = EXPECTED_RESPONSE
    #: False when the conversation behind the ticket is gone (soft-deleted): the ticket
    #: still exists and stays auditable, but no transcript can be produced for it.
    transcript_available: bool = True
    #: Raw assignee id. Never serialised (responses only carry ``assigned_to_masked``) but
    #: needed to decide whether the caller is the agent who actually took the ticket over.
    assigned_to: UUID | None = None


@dataclass(frozen=True, slots=True)
class SupportMessageRow:
    message_id: UUID
    role: str
    content: str
    is_complete: bool
    citations: list[Any]
    risk: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupportToolCallRow:
    tool_call_id: UUID
    tool_name: str
    status: str
    latency_ms: int
    result_summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SupportConversationRow:
    conversation_id: UUID
    title: str
    owner_reference_masked: str
    target_user_id: UUID
    ticket_id: UUID
    ticket_status: str
    ticket_primary_reason_code: str
    messages: tuple[SupportMessageRow, ...] = field(default_factory=tuple)
    tool_calls: tuple[SupportToolCallRow, ...] = field(default_factory=tuple)


def _waiting_seconds(created_at: datetime, now: datetime) -> int:
    delta = now - created_at
    return max(0, int(delta.total_seconds()))


def _ticket_row(
    row: HandoffTicket,
    *,
    owner_masked: str | None,
    assignee_masked: str | None,
    now: datetime,
    transcript_available: bool = True,
) -> SupportTicketRow:
    reason_codes = (
        list(row.risk_rule_codes_jsonb) if isinstance(row.risk_rule_codes_jsonb, list) else []
    )
    risk_level = str(row.risk_level)
    return SupportTicketRow(
        ticket_id=row.id,
        status=str(row.status),
        risk_level=risk_level,
        primary_reason_code=row.primary_reason_code,
        reason_codes=tuple(str(code) for code in reason_codes),
        priority=row.priority,
        queue=queue_for(risk_level),
        conversation_id=row.conversation_id,
        user_reference_masked=mask_reference(row.user_id, owner_masked) or "user-****--",
        assigned_to_masked=mask_reference(row.assigned_to, assignee_masked),
        created_at=row.created_at,
        updated_at=row.updated_at,
        waiting_seconds=_waiting_seconds(row.created_at, now),
        summary_redacted=row.summary_redacted,
        transcript_available=transcript_available,
        assigned_to=row.assigned_to,
    )


def _risk_payload(payload: Any) -> dict[str, Any]:
    """Project the stored risk blob onto the fields the workbench UI reads.

    ``messages.risk_jsonb`` mixes two shapes: the chat output guard writes
    ``risk_level``/``primary_reason_code``, older rows carry ``level``/``rule_codes``, and a
    human reply carries ``author="support_agent"``. Returning all of them (instead of only
    ``level``) keeps the risk badge and the "人工客服" attribution working.
    """
    if not isinstance(payload, dict):
        return {}
    level = payload.get("risk_level") or payload.get("level")
    codes = payload.get("rule_codes")
    return {
        "risk_level": str(level) if level else None,
        "level": str(level) if level else None,
        "primary_reason_code": payload.get("primary_reason_code"),
        "handoff_required": payload.get("handoff_required"),
        "author": payload.get("author"),
        "agent_reference_masked": payload.get("agent_reference_masked"),
        "rule_codes": [str(code) for code in codes] if isinstance(codes, list) else [],
    }


class SupportRepository:
    """Shop-scoped reads and state changes for the support workbench."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- queue ------------------------------------------------------------
    async def list_tickets(
        self,
        *,
        shop_id: UUID,
        status: str | None = None,
        risk_level: str | None = None,
        transcript: str = "available",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[SupportTicketRow, ...]:
        """Return the ticket queue: unresolved first, then highest risk, then longest waiting.

        ``closed`` tickets are pushed behind every live one. Sorting purely by risk/age put
        four-day-old closed tickets at the top of the first page, so a ticket the shopper
        had just escalated never appeared in the workbench (the page only loads ``limit``
        rows): a closed ticket needs no agent, an open one does.

        ``transcript="available"`` (default) hides tickets whose conversation is gone:
        those rows are real and auditable, but an agent can never open them, so showing
        them by default turns the queue into noise. ``transcript="all"`` brings them back
        flagged with ``transcript_available=False``.
        """
        if transcript not in ("available", "all"):
            raise ValueError(f"unknown transcript filter: {transcript!r}")
        owner = sa.orm.aliased(User)
        assignee = sa.orm.aliased(User)
        # 0 for anything an agent can still work on (open/assigned/resolved), 1 for closed.
        unresolved = sa.case((HandoffTicket.status == HandoffStatus.CLOSED, 1), else_=0)
        severity = sa.case(
            (HandoffTicket.risk_level == "critical", 0),
            (HandoffTicket.risk_level == "high", 1),
            (HandoffTicket.risk_level == "medium", 2),
            else_=3,
        )
        live_transcript = sa.and_(
            Conversation.shop_id == HandoffTicket.shop_id,
            Conversation.id == HandoffTicket.conversation_id,
            Conversation.deleted_at.is_(None),
        )
        stmt = (
            sa.select(
                HandoffTicket,
                owner.display_name_masked,
                assignee.display_name_masked,
                Conversation.id.is_not(None).label("transcript_available"),
            )
            .outerjoin(Conversation, live_transcript)
            .outerjoin(
                owner,
                sa.and_(owner.shop_id == HandoffTicket.shop_id, owner.id == HandoffTicket.user_id),
            )
            .outerjoin(
                assignee,
                sa.and_(
                    assignee.shop_id == HandoffTicket.shop_id,
                    assignee.id == HandoffTicket.assigned_to,
                ),
            )
            .where(HandoffTicket.shop_id == shop_id)
            .order_by(unresolved, severity, HandoffTicket.created_at, HandoffTicket.id)
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(HandoffTicket.status == HandoffStatus(status))
        if risk_level is not None:
            stmt = stmt.where(HandoffTicket.risk_level == risk_level)
        if transcript == "available":
            stmt = stmt.where(Conversation.id.is_not(None))
        now = datetime.now(UTC)
        rows = (await self._session.execute(stmt)).all()
        return tuple(
            _ticket_row(
                ticket,
                owner_masked=owner_name,
                assignee_masked=assignee_name,
                now=now,
                transcript_available=bool(available),
            )
            for ticket, owner_name, assignee_name, available in rows
        )

    async def conversation_state(self, *, shop_id: UUID, conversation_id: UUID) -> str:
        """Return ``"live"`` / ``"deleted"`` / ``"missing"`` for a conversation.

        Used to tell an agent *why* a transcript is unavailable instead of answering every
        case with the same "not found".
        """
        row = (
            await self._session.execute(
                sa.select(Conversation.deleted_at).where(
                    Conversation.shop_id == shop_id, Conversation.id == conversation_id
                )
            )
        ).first()
        if row is None:
            return "missing"
        return "deleted" if row[0] is not None else "live"

    async def get_ticket(self, *, shop_id: UUID, ticket_id: UUID) -> SupportTicketRow | None:
        owner = sa.orm.aliased(User)
        assignee = sa.orm.aliased(User)
        stmt = (
            sa.select(HandoffTicket, owner.display_name_masked, assignee.display_name_masked)
            .outerjoin(
                owner,
                sa.and_(owner.shop_id == HandoffTicket.shop_id, owner.id == HandoffTicket.user_id),
            )
            .outerjoin(
                assignee,
                sa.and_(
                    assignee.shop_id == HandoffTicket.shop_id,
                    assignee.id == HandoffTicket.assigned_to,
                ),
            )
            .where(HandoffTicket.shop_id == shop_id, HandoffTicket.id == ticket_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        ticket, owner_name, assignee_name = row
        return _ticket_row(
            ticket,
            owner_masked=owner_name,
            assignee_masked=assignee_name,
            now=datetime.now(UTC),
            transcript_available=await self.conversation_state(
                shop_id=shop_id, conversation_id=ticket.conversation_id
            )
            == "live",
        )

    # -- state machine ----------------------------------------------------
    async def assignee_is_elevated(self, *, shop_id: UUID, user_id: UUID) -> bool:
        """Return True when ``user_id`` is a support/admin account of this shop."""
        role = await self._session.scalar(
            sa.select(User.role).where(User.shop_id == shop_id, User.id == user_id)
        )
        return role in ELEVATED_ROLES

    async def transition(
        self,
        *,
        shop_id: UUID,
        ticket_id: UUID,
        actor_user_id: UUID,
        action: str,
        assignee_user_id: UUID | None = None,
        resolution_summary: str | None = None,
        close_reason: str | None = None,
    ) -> SupportTicketRow:
        """Apply one legal transition or raise :class:`InvalidTicketTransition`.

        The row is locked with ``SELECT ... FOR UPDATE`` so two agents cannot both move
        the same ticket into an inconsistent state.
        """
        ticket = (
            await self._session.execute(
                sa.select(HandoffTicket)
                .where(HandoffTicket.shop_id == shop_id, HandoffTicket.id == ticket_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if ticket is None:
            raise InvalidTicketTransition("ticket not found")

        allowed, target = TRANSITIONS[action]
        if HandoffStatus(str(ticket.status)) not in allowed:
            raise InvalidTicketTransition(f"{ticket.status} -> {target.value}")

        if action == "assign":
            assignee = assignee_user_id or actor_user_id
            if not await self.assignee_is_elevated(shop_id=shop_id, user_id=assignee):
                raise UnknownAssignee(str(assignee))
            ticket.assigned_to = assignee
        elif action == "resolve":
            ticket.resolution_summary = resolution_summary
            ticket.resolved_at = datetime.now(UTC)
        elif action == "archive":
            reason = (close_reason or "").strip()
            if not reason:
                raise InvalidTicketTransition("archive requires a close_reason")
            ticket.close_reason = reason
            ticket.resolved_at = ticket.resolved_at or datetime.now(UTC)
        else:
            ticket.close_reason = close_reason

        ticket.status = target
        await self._session.execute(
            sa.update(HandoffTicket)
            .where(HandoffTicket.shop_id == shop_id, HandoffTicket.id == ticket_id)
            .values(
                status=ticket.status,
                assigned_to=ticket.assigned_to,
                resolution_summary=ticket.resolution_summary,
                resolved_at=ticket.resolved_at,
                close_reason=ticket.close_reason,
                updated_at=sa.func.now(),
            )
        )
        await self._session.commit()

        refreshed = await self.get_ticket(shop_id=shop_id, ticket_id=ticket_id)
        assert refreshed is not None  # the row was just locked and updated
        return refreshed

    # -- conversation -----------------------------------------------------
    async def get_ticket_for_conversation(
        self, *, shop_id: UUID, conversation_id: UUID
    ) -> HandoffTicket | None:
        """Return the authorising ticket for a conversation, if this shop has one.

        A conversation is only readable by an agent *because* a ticket exists for it;
        without a ticket there is no business reason to look at the transcript.
        """
        stmt = (
            sa.select(HandoffTicket)
            .where(
                HandoffTicket.shop_id == shop_id,
                HandoffTicket.conversation_id == conversation_id,
            )
            .order_by(HandoffTicket.created_at.desc(), HandoffTicket.id)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def get_conversation(
        self,
        *,
        shop_id: UUID,
        conversation_id: UUID,
        ticket: HandoffTicket,
        message_limit: int = 100,
    ) -> SupportConversationRow | None:
        """Return the authorised transcript with citations, risk and tool summaries."""
        conversation = (
            await self._session.execute(
                sa.select(Conversation, User.display_name_masked)
                .outerjoin(
                    User,
                    sa.and_(User.shop_id == Conversation.shop_id, User.id == Conversation.user_id),
                )
                .where(
                    Conversation.shop_id == shop_id,
                    Conversation.id == conversation_id,
                    Conversation.deleted_at.is_(None),
                )
            )
        ).first()
        if conversation is None:
            return None
        row, owner_name = conversation

        messages = (
            (
                await self._session.execute(
                    sa.select(Message)
                    .where(Message.shop_id == shop_id, Message.conversation_id == conversation_id)
                    .order_by(Message.created_at, Message.id)
                    .limit(message_limit)
                )
            )
            .scalars()
            .all()
        )
        tool_calls = (
            (
                await self._session.execute(
                    sa.select(ToolCall)
                    .where(ToolCall.shop_id == shop_id, ToolCall.conversation_id == conversation_id)
                    .order_by(ToolCall.created_at, ToolCall.id)
                    .limit(message_limit)
                )
            )
            .scalars()
            .all()
        )

        return SupportConversationRow(
            conversation_id=row.id,
            title=row.title,
            owner_reference_masked=mask_reference(row.user_id, owner_name) or "user-****--",
            target_user_id=row.user_id,
            ticket_id=ticket.id,
            ticket_status=str(ticket.status),
            ticket_primary_reason_code=ticket.primary_reason_code,
            messages=tuple(
                SupportMessageRow(
                    message_id=message.id,
                    role=str(message.role),
                    # Defence in depth: never echo unredacted PII even if it was stored.
                    content=mask_pii(message.content)[0],
                    is_complete=bool(message.is_complete),
                    citations=(
                        list(message.citations_jsonb)
                        if isinstance(message.citations_jsonb, list)
                        else []
                    ),
                    risk=_risk_payload(message.risk_jsonb),
                    created_at=message.created_at,
                )
                for message in messages
            ),
            tool_calls=tuple(
                SupportToolCallRow(
                    tool_call_id=call.id,
                    tool_name=call.tool_name,
                    status=str(call.status),
                    latency_ms=int(call.latency_ms or 0),
                    result_summary=(
                        dict(call.result_summary_jsonb)
                        if isinstance(call.result_summary_jsonb, dict)
                        else {}
                    ),
                )
                for call in tool_calls
            ),
        )

    # -- quality labels ---------------------------------------------------
    async def get_authorised_assistant_message(
        self, *, shop_id: UUID, message_id: UUID
    ) -> Message | None:
        """Return the assistant message only when a ticket in this shop covers it."""
        message = (
            await self._session.execute(
                sa.select(Message).where(Message.shop_id == shop_id, Message.id == message_id)
            )
        ).scalar_one_or_none()
        if message is None or str(message.role) != "assistant":
            return None
        ticket = await self.get_ticket_for_conversation(
            shop_id=shop_id, conversation_id=message.conversation_id
        )
        return message if ticket is not None else None

    async def upsert_quality_label(
        self,
        *,
        shop_id: UUID,
        ticket_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        label: str,
        reason_summary: str | None,
        labeled_by: UUID,
    ) -> SupportQualityLabel:
        """Record or replace this agent's verdict on one assistant answer."""
        existing = (
            await self._session.execute(
                sa.select(SupportQualityLabel).where(
                    SupportQualityLabel.shop_id == shop_id,
                    SupportQualityLabel.message_id == message_id,
                    SupportQualityLabel.labeled_by == labeled_by,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.label = label
            existing.reason_summary = reason_summary
            await self._session.execute(
                sa.update(SupportQualityLabel)
                .where(SupportQualityLabel.id == existing.id)
                .values(label=label, reason_summary=reason_summary, updated_at=sa.func.now())
            )
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        row = SupportQualityLabel(
            shop_id=shop_id,
            ticket_id=ticket_id,
            conversation_id=conversation_id,
            message_id=message_id,
            label=label,
            reason_summary=reason_summary,
            labeled_by=labeled_by,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row


__all__ = [
    "ELEVATED_ROLES",
    "TRANSITIONS",
    "InvalidTicketTransition",
    "SupportConversationRow",
    "SupportMessageRow",
    "SupportRepository",
    "SupportTicketRow",
    "SupportToolCallRow",
    "UnknownAssignee",
    "mask_reference",
    "queue_for",
]
