"""Async SQLAlchemy engine and session factory helpers."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shopmate_ecommerce_assistant.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the application's async PostgreSQL engine."""
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async sessions that do not expire committed attributes eagerly."""
    return async_sessionmaker(engine, expire_on_commit=False)
