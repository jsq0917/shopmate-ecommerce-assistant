"""Conversation and message persistence for the chat API.

Both repositories are shop- and user-scoped by construction: a missing conversation and a
conversation belonging to another user are indistinguishable, so callers never leak
resource existence. Message idempotency uses the partial unique index
``uq_messages_client``; a duplicate client message is reported, never double-written.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import Conversation, Message
from shopmate_ecommerce_assistant.db.models.enums import MessageRole


@dataclass(frozen=True, slots=True)
class ConversationRow:
    """One conversation as rendered to the API."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRow:
    """One chat message as rendered to the API."""

    id: UUID
    role: str
    content: str
    route: str | None
    finish_reason: str | None
    citations: dict[str, Any]
    risk: dict[str, Any]
    cards: list[Any]
    is_complete: bool
    created_at: datetime
    client_message_id: UUID | None


def _encode_cursor(stamp: datetime, resource_id: UUID) -> str:
    raw = f"{stamp.isoformat()}|{resource_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        stamp_str, resource_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(stamp_str), UUID(resource_id)
    except (ValueError, TypeError):
        return None


def _content_hash(content: str) -> bytes:
    return hashlib.sha256(content.encode("utf-8")).digest()


class ConversationRepository:
    """Conversation list/create/rename/soft-delete, keyset paginated."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[ConversationRow], str | None]:
        """Return non-deleted conversations for the user, newest activity first."""
        stmt = (
            sa.select(Conversation)
            .where(
                Conversation.shop_id == shop_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .limit(limit + 1)
        )
        key = _decode_cursor(cursor)
        if key is not None:
            stamp, resource_id = key
            stmt = stmt.where(
                sa.or_(
                    Conversation.updated_at < stamp,
                    sa.and_(Conversation.updated_at == stamp, Conversation.id < resource_id),
                )
            )
        rows = (await self._session.execute(stmt)).scalars().all()

        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_cursor(last.updated_at, last.id)
        return [self._to_row(row) for row in page], next_cursor

    async def create(self, *, shop_id: UUID, user_id: UUID, title: str) -> ConversationRow:
        """Create a conversation for the user and return it."""
        row = Conversation(shop_id=shop_id, user_id=user_id, title=title)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_row(row)

    async def get(
        self, *, shop_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> ConversationRow | None:
        """Return a live conversation owned by the user, or ``None``."""
        stmt = sa.select(Conversation).where(
            Conversation.shop_id == shop_id,
            Conversation.user_id == user_id,
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else self._to_row(row)

    async def rename(
        self, *, shop_id: UUID, user_id: UUID, conversation_id: UUID, title: str
    ) -> bool:
        """Rename a conversation; return True when it existed and belonged to the user."""
        result = await self._session.execute(
            sa.update(Conversation)
            .where(
                Conversation.shop_id == shop_id,
                Conversation.user_id == user_id,
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
            .values(title=title)
        )
        await self._session.commit()
        return result.rowcount == 1

    async def soft_delete(self, *, shop_id: UUID, user_id: UUID, conversation_id: UUID) -> bool:
        """Soft-delete a conversation; return True when it existed and belonged."""
        result = await self._session.execute(
            sa.update(Conversation)
            .where(
                Conversation.shop_id == shop_id,
                Conversation.user_id == user_id,
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        await self._session.commit()
        return result.rowcount == 1

    @staticmethod
    def _to_row(row: Conversation) -> ConversationRow:
        return ConversationRow(
            id=row.id, title=row.title, created_at=row.created_at, updated_at=row.updated_at
        )


class MessageRepository:
    """Message persistence with client-message idempotency and append-once assistant rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_client_message_id(
        self, *, shop_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> MessageRow | None:
        """Return the user message already stored under a client message id, if any."""
        stmt = sa.select(Message).where(
            Message.shop_id == shop_id,
            Message.conversation_id == conversation_id,
            Message.client_message_id == client_message_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else self._to_row(row)

    async def insert_user_message(
        self,
        *,
        shop_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        content: str,
        client_message_id: UUID,
    ) -> MessageRow:
        """Insert the user message; a duplicate client id raises ``MessageConflictError``."""
        row = Message(
            shop_id=shop_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.USER,
            content=content,
            content_hash=_content_hash(content),
            client_message_id=client_message_id,
            is_complete=True,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise MessageConflictError("duplicate client message") from exc
        await self._session.refresh(row)
        return self._to_row(row)

    async def insert_assistant_message(
        self,
        *,
        shop_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        content: str,
        route: str | None,
        finish_reason: str | None,
        citations: dict[str, Any],
        risk: dict[str, Any],
        is_complete: bool,
        cards: list[Any] | None = None,
    ) -> MessageRow:
        """Insert the final assistant message once, at stream termination."""
        row = Message(
            shop_id=shop_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.ASSISTANT,
            content=content,
            content_hash=_content_hash(content),
            route=route,
            finish_reason=finish_reason,
            citations_jsonb=citations,
            risk_jsonb=risk,
            cards_jsonb=list(cards or []),
            is_complete=is_complete,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_row(row)

    async def list_history(
        self,
        *,
        shop_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        limit: int = 100,
        before: str | None = None,
    ) -> list[MessageRow]:
        """Return messages in ascending order, optionally before a cursor."""
        stmt = (
            sa.select(Message)
            .where(
                Message.shop_id == shop_id,
                Message.conversation_id == conversation_id,
                Message.user_id == user_id,
            )
            .order_by(Message.created_at.asc(), Message.id)
            .limit(limit)
        )
        key = _decode_cursor(before)
        if key is not None:
            stamp, resource_id = key
            stmt = stmt.where(
                sa.or_(
                    Message.created_at < stamp,
                    sa.and_(Message.created_at == stamp, Message.id < resource_id),
                )
            )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_row(row) for row in rows]

    @staticmethod
    def _to_row(row: Message) -> MessageRow:
        return MessageRow(
            id=row.id,
            role=str(row.role),
            content=row.content,
            route=row.route,
            finish_reason=row.finish_reason,
            citations=row.citations_jsonb if isinstance(row.citations_jsonb, dict) else {},
            risk=row.risk_jsonb if isinstance(row.risk_jsonb, dict) else {},
            cards=list(row.cards_jsonb) if isinstance(row.cards_jsonb, list) else [],
            is_complete=bool(row.is_complete),
            created_at=row.created_at,
            client_message_id=row.client_message_id,
        )


class MessageConflictError(Exception):
    """Raised when a user message with the same client id already exists."""


__all__ = [
    "ConversationRepository",
    "ConversationRow",
    "MessageConflictError",
    "MessageRepository",
    "MessageRow",
]
