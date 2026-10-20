"""Authentication persistence: users and rotated refresh sessions.

Every query is shop-scoped; e-mail lookup is case-insensitive (matching the unique index)
and returns ``None`` for both "missing" and "wrong shop" so the caller can emit the same
non-leaking response either way.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import RefreshSession, Shop, User
from shopmate_ecommerce_assistant.db.models.enums import UserRole


class UserRepository:
    """User account reads/writes, always scoped to a shop."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_default_shop_id(self) -> UUID:
        """Return the single demo shop id (MVP runs one tenant)."""
        stmt = sa.select(Shop.id).order_by(Shop.created_at, Shop.id).limit(1)
        shop_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if shop_id is None:
            raise RuntimeError("no shop seeded; run scripts/seed.py first")
        return shop_id

    async def get_by_email(self, *, shop_id: UUID, email: str) -> User | None:
        """Return the user by case-insensitive e-mail inside the shop, or ``None``."""
        stmt = sa.select(User).where(
            User.shop_id == shop_id,
            sa.func.lower(User.email_ci) == email.strip().lower(),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get(self, *, shop_id: UUID, user_id: UUID) -> User | None:
        """Return one user inside the shop, or ``None``."""
        stmt = sa.select(User).where(User.shop_id == shop_id, User.id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        shop_id: UUID,
        email: str,
        password_hash: str,
        role: UserRole,
        display_name_masked: str,
    ) -> User:
        """Insert one user and commit; a duplicate e-mail raises ``IntegrityError``."""
        row = User(
            shop_id=shop_id,
            email_ci=email.strip().lower(),
            password_hash=password_hash,
            role=role,
            display_name_masked=display_name_masked,
            is_active=True,
            is_synthetic=True,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def touch_last_login(self, *, shop_id: UUID, user_id: UUID) -> None:
        """Record a successful login timestamp (best-effort, not critical-path)."""
        await self._session.execute(
            sa.update(User)
            .where(User.shop_id == shop_id, User.id == user_id)
            .values(last_login_at=datetime.now(UTC))
        )
        await self._session.commit()


class RefreshSessionRepository:
    """Hashed, rotated refresh-token session store."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        token_hash: bytes,
        csrf_token_hash: bytes,
        expires_at: datetime,
    ) -> RefreshSession:
        """Insert a new refresh session and commit."""
        row = RefreshSession(
            shop_id=shop_id,
            user_id=user_id,
            token_hash=token_hash,
            csrf_token_hash=csrf_token_hash,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get_active(self, *, token_hash: bytes) -> RefreshSession | None:
        """Return an unexpired, unrevoked session matching the token hash."""
        now = datetime.now(UTC)
        stmt = sa.select(RefreshSession).where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, *, session_id: UUID) -> None:
        """Revoke a refresh session (logout / replay detection)."""
        await self._session.execute(
            sa.update(RefreshSession)
            .where(RefreshSession.id == session_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await self._session.commit()

    async def rotate(
        self,
        *,
        session_id: UUID,
        replaced_by_id: UUID,
    ) -> None:
        """Mark the old session as consumed by a newer one (rotation on use)."""
        await self._session.execute(
            sa.update(RefreshSession)
            .where(RefreshSession.id == session_id)
            .values(revoked_at=datetime.now(UTC), replaced_by_id=replaced_by_id)
        )
        await self._session.commit()


__all__ = ["RefreshSessionRepository", "UserRepository"]
