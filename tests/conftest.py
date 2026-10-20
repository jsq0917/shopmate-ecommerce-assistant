"""Shared fixtures for unit and integration tests.

Integration fixtures skip (with an explicit reason) when Docker services are not running,
so CI without infrastructure still exercises the pure logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return the process settings (defaults match the local Compose stack)."""
    return get_settings()


@pytest.fixture
async def session(settings: Settings) -> AsyncIterator[AsyncSession]:
    """Yield an async session or skip when PostgreSQL is unreachable."""
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用：跳过集成测试")
    factory = create_session_factory(engine)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()
