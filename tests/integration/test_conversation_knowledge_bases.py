"""Conversation-scoped knowledge-base selection over the real API (stage 18).

Covers the contract in ``docs/06-api.md`` §6.1:

* a conversation remembers one or more knowledge bases (empty = no restriction);
* switching the selection affects the next turn only — history keeps its citations;
* a knowledge base from another shop (or an inactive one) is rejected as a whole request;
* the chat stream hands the selection to the retriever as an explicit ``RetrievalScope``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter
from shopmate_ecommerce_assistant.db.models import KnowledgeBase, KnowledgeBaseStatus, Shop
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app

pytestmark = pytest.mark.integration

#: Rows this module creates are deleted in teardown: these tests run against whatever
#: ``DATABASE_URL`` points at (the demo database by default), and the chat page lists
#: knowledge bases, so leftover fixtures would show up in the UI.
_CREATED: list[tuple[str, UUID]] = []

_CAPTCHA_RE = re.compile(r"(\d+)\s*\+\s*(\d+)\s*=\s*\?")


def _solve(question: str) -> str:
    match = _CAPTCHA_RE.search(question)
    assert match, f"无法解析验证码题目：{question}"
    return str(int(match.group(1)) + int(match.group(2)))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _ScopedPolicy:
    """Records the scope it was called with and answers with one grounded citation."""

    def __init__(self) -> None:
        self.scopes: list[object] = []
        self.generations: list[object] = []

    async def answer(self, question, scope, *, query_plan=None, generation=None, risk_level=None):
        self.scopes.append(scope)
        self.generations.append(generation)
        return SimpleNamespace(
            answer_text="七天无理由退货需保持商品完好 [c1]。",
            citations=(),
            status="answered",
            used_labels=("c1",),
            reasons=(),
        )


@asynccontextmanager
async def _client(policy: _ScopedPolicy) -> AsyncIterator[httpx.AsyncClient]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
            await connection.execute(sa.text("select 1 from conversations limit 1"))
    except Exception:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用或未执行 alembic upgrade head：跳过")

    factory = create_session_factory(engine)
    app = create_app(settings)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.policy = policy
    app.state.policy_factory = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def _login(client: httpx.AsyncClient) -> tuple[str, UUID]:
    """Register a fresh shopper, return (token, shop_id)."""
    email = f"kb-{uuid4().hex[:12]}@example.invalid"
    password = "correct horse battery"
    captcha = (await client.get("/api/v1/auth/captcha")).json()["data"]
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "captcha_token": captcha["captcha_token"],
            "captcha_answer": _solve(captcha["question"]),
        },
    )
    assert register.status_code == 201, register.text
    captcha = (await client.get("/api/v1/auth/captcha")).json()["data"]
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": captcha["captcha_token"],
            "captcha_answer": _solve(captcha["question"]),
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()["data"]
    return token, UUID(me["shop_id"])


@pytest.fixture(scope="module", autouse=True)
async def _cleanup_created_rows() -> AsyncIterator[None]:
    yield
    if not _CREATED:
        return
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            for table, row_id in reversed(_CREATED):
                await session.execute(
                    sa.text(f"delete from {table} where id = :id"), {"id": row_id}
                )
            await session.commit()
    finally:
        await engine.dispose()


async def _insert_kb(shop_id: UUID, name: str, *, status: KnowledgeBaseStatus) -> UUID:
    """Insert one knowledge base. Names are unique per shop, so each call gets a suffix."""
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    kb_id = uuid4()
    try:
        async with factory() as session:
            session.add(
                KnowledgeBase(
                    id=kb_id,
                    shop_id=shop_id,
                    name=f"{name}-{uuid4().hex[:8]}",
                    locale="zh-CN",
                    region="CN",
                    status=status,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()
    _CREATED.append(("knowledge_bases", kb_id))
    return kb_id


async def _insert_shop() -> UUID:
    """Insert a second tenant so cross-shop rejections use a real foreign key."""
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    shop_id = uuid4()
    try:
        async with factory() as session:
            session.add(Shop(id=shop_id, name=f"other-{uuid4().hex[:8]}"))
            await session.commit()
    finally:
        await engine.dispose()
    _CREATED.append(("shops", shop_id))
    return shop_id


async def test_patch_persists_and_returns_the_selection() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token, shop_id = await _login(client)
        kb_a = await _insert_kb(shop_id, "kb-a", status=KnowledgeBaseStatus.ACTIVE)
        kb_b = await _insert_kb(shop_id, "kb-b", status=KnowledgeBaseStatus.ACTIVE)

        created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
        conversation_id = created.json()["data"]["id"]
        assert created.json()["data"]["knowledge_base_ids"] == []

        patched = await client.patch(
            f"/api/v1/conversations/{conversation_id}/knowledge-bases",
            json={"knowledge_base_ids": [str(kb_a), str(kb_b)]},
            headers=_auth(token),
        )
        assert patched.status_code == 200, patched.text
        assert sorted(patched.json()["data"]["knowledge_base_ids"]) == sorted(
            [str(kb_a), str(kb_b)]
        )

        # Idempotent re-read: the list endpoint returns the stored selection.
        listed = await client.get("/api/v1/conversations", headers=_auth(token))
        item = next(i for i in listed.json()["data"]["items"] if i["id"] == conversation_id)
        assert len(item["knowledge_base_ids"]) == 2

        # Duplicates collapse, order is not semantic.
        again = await client.patch(
            f"/api/v1/conversations/{conversation_id}/knowledge-bases",
            json={"knowledge_base_ids": [str(kb_b), str(kb_b)]},
            headers=_auth(token),
        )
        assert again.json()["data"]["knowledge_base_ids"] == [str(kb_b)]

        # Empty list restores "no restriction".
        cleared = await client.patch(
            f"/api/v1/conversations/{conversation_id}/knowledge-bases",
            json={"knowledge_base_ids": []},
            headers=_auth(token),
        )
        assert cleared.json()["data"]["knowledge_base_ids"] == []


async def test_rejects_another_shops_or_archived_knowledge_base() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token, shop_id = await _login(client)
        other_shop = await _insert_shop()
        other_shop_kb = await _insert_kb(
            other_shop, "kb-other-shop", status=KnowledgeBaseStatus.ACTIVE
        )
        archived = await _insert_kb(shop_id, "kb-archived", status=KnowledgeBaseStatus.ARCHIVED)
        good = await _insert_kb(shop_id, "kb-good", status=KnowledgeBaseStatus.ACTIVE)
        created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
        conversation_id = created.json()["data"]["id"]

        for bad in (other_shop_kb, archived, uuid4()):
            response = await client.patch(
                f"/api/v1/conversations/{conversation_id}/knowledge-bases",
                json={"knowledge_base_ids": [str(good), str(bad)]},
                headers=_auth(token),
            )
            assert response.status_code == 422, response.text
            assert response.json()["error"]["code"] == "KNOWLEDGE_BASE_NOT_SELECTABLE"

        # A rejected request must not persist a partial selection.
        detail = await client.get("/api/v1/conversations", headers=_auth(token))
        item = next(i for i in detail.json()["data"]["items"] if i["id"] == conversation_id)
        assert item["knowledge_base_ids"] == []


async def test_selection_of_another_users_conversation_is_not_found() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        owner_token, _ = await _login(client)
        intruder_token, _ = await _login(client)
        created = await client.post("/api/v1/conversations", json={}, headers=_auth(owner_token))
        conversation_id = created.json()["data"]["id"]
        response = await client.patch(
            f"/api/v1/conversations/{conversation_id}/knowledge-bases",
            json={"knowledge_base_ids": []},
            headers=_auth(intruder_token),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_chat_stream_hands_the_selection_to_the_retriever() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token, shop_id = await _login(client)
        kb = await _insert_kb(shop_id, "kb-stream", status=KnowledgeBaseStatus.ACTIVE)
        created = await client.post(
            "/api/v1/conversations",
            json={"knowledge_base_ids": [str(kb)]},
            headers=_auth(token),
        )
        assert created.json()["data"]["knowledge_base_ids"] == [str(kb)]
        conversation_id = created.json()["data"]["id"]

        await client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation_id,
                "message": "退货政策是怎么规定的？",
                "client_message_id": str(uuid4()),
            },
            headers=_auth(token),
        )
        assert policy.scopes, "the policy service should have been called"
        scope = policy.scopes[-1]
        assert scope.knowledge_base_ids == (str(kb),)
        # An explicit selection replaces the implicit locale/region narrowing.
        assert scope.locale is None and scope.region is None

        # Clearing the selection restores the pre-stage-18 scope (shop + defaults).
        await client.patch(
            f"/api/v1/conversations/{conversation_id}/knowledge-bases",
            json={"knowledge_base_ids": []},
            headers=_auth(token),
        )
        await client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation_id,
                "message": "退货政策是怎么规定的？",
                "client_message_id": str(uuid4()),
            },
            headers=_auth(token),
        )
        scope = policy.scopes[-1]
        assert scope.knowledge_base_ids == ()
        assert (scope.locale, scope.region) == ("zh-CN", "CN")


async def test_knowledge_base_picker_lists_only_active_bases_of_the_shop() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token, shop_id = await _login(client)
        other_shop = await _insert_shop()
        active = await _insert_kb(shop_id, "kb-pick-me", status=KnowledgeBaseStatus.ACTIVE)
        await _insert_kb(shop_id, "kb-archived-hidden", status=KnowledgeBaseStatus.ARCHIVED)
        await _insert_kb(other_shop, "kb-other-shop-hidden", status=KnowledgeBaseStatus.ACTIVE)

        response = await client.get("/api/v1/knowledge-bases", headers=_auth(token))
        assert response.status_code == 200, response.text
        ids = [item["id"] for item in response.json()["data"]["items"]]
        assert str(active) in ids
        assert all("archived" not in item["name"] for item in response.json()["data"]["items"])
        assert all("other-shop" not in item["name"] for item in response.json()["data"]["items"])
