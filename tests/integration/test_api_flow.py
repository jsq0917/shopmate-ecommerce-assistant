"""End-to-end API flow tests (require PostgreSQL + ``alembic upgrade head``).

These exercise the stage-10 surface over a real database: captcha/register/login, JWT,
conversation CRUD, SSE chat (including citations and terminal errors), cross-tenant
isolation, idempotency and CSRF/refresh rotation. They skip cleanly when PostgreSQL is not
reachable.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app
from shopmate_ecommerce_assistant.rag.citations import Citation
from shopmate_ecommerce_assistant.synthetic.catalog_data import build_dataset
from shopmate_ecommerce_assistant.synthetic.seed import seed_database, write_source_files
from shopmate_ecommerce_assistant.tools.dispatcher import ToolDispatcher
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _rendered_knowledge_files() -> None:
    """Render the knowledge source files once per module.

    ``run_seed`` rewrites every policy document (PDF/DOCX/Markdown) on each call. Doing
    that once per test made Windows intermittently fail with ``OSError: [Errno 22]`` inside
    ``open()`` — a file-locking artefact of rewriting the same paths repeatedly in a row,
    not a product defect. The database seed itself still runs per test, and ``run_seed``
    keeps its own coverage in ``test_seed_data.py``.
    """
    write_source_files()


_CAPTCHA_RE = re.compile(r"(\d+)\s*\+\s*(\d+)\s*=\s*\?")


def _solve(question: str) -> str:
    match = _CAPTCHA_RE.search(question)
    assert match, f"无法解析验证码题目：{question}"
    return str(int(match.group(1)) + int(match.group(2)))


def _fake_citation() -> Citation:
    """One grounded citation, as the stage-7 retriever would build it."""
    return Citation(
        citation_id="cit_0000000000000001",
        label="c1",
        document_id=uuid4(),
        chunk_id=uuid4(),
        version_id=uuid4(),
        title="退换货政策",
        heading="七天无理由退货",
        page_no=2,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00",
        effective_to=None,
        snippet="合成政策片段：自签收之日起七天内可申请无理由退货，商品需保持完好。",
        score=0.71,
        dense_similarity=0.71,
    )


class _FakePolicyService:
    """Stands in for the wired RAG path (Milvus/LLM are not part of API tests).

    Returns one grounded answer with a single citation so the ``citation`` SSE event and
    its persistence can be verified end to end.
    """

    async def answer(self, question, scope, *, query_plan=None):
        return SimpleNamespace(
            answer_text="七天无理由退货需保持商品完好 [c1]。",
            citations=(_fake_citation(),),
        )


def _fake_policy_factory():
    """A policy factory in the shape ``main._build_policy_factory`` returns.

    The factory is bound to the session of the request being served; returning a service
    that ignores it is fine here because the point is to prove the endpoint prefers the
    factory over a static service.
    """

    def build(session):
        assert session is not None, "the policy service must be bound to the request session"
        return _FakePolicyService()

    return build


def _parse_sse(raw: str) -> list[dict]:
    """Parse an SSE body into business events, checking frame/type consistency."""
    events: list[dict] = []
    for block in raw.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        assert data is not None, f"SSE frame without data: {block!r}"
        payload = json.loads(data)
        assert payload["type"] == event_type, "event name must match the payload type"
        assert payload["event_id"] == str(payload["sequence"]), "id must equal sequence"
        events.append(payload)
    return events


@asynccontextmanager
async def _api_client(*, policy=None, policy_factory=None) -> AsyncIterator[httpx.AsyncClient]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用：跳过 API 集成测试")

    factory = create_session_factory(engine)
    async with factory() as session:
        await seed_database(session, build_dataset())

    app = create_app(settings)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.rate_limiter = InMemoryRateLimiter()
    # No wiring is installed by default: the chat endpoint falls back to these overrides,
    # which keeps the RAG path injectable without Milvus or an LLM.
    app.state.policy = policy
    app.state.policy_factory = policy_factory

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with _api_client() as client:
        yield client


@pytest.fixture
async def api_client_with_policy() -> AsyncIterator[httpx.AsyncClient]:
    async with _api_client(policy=_FakePolicyService()) as client:
        yield client


@pytest.fixture
async def api_client_with_policy_factory() -> AsyncIterator[httpx.AsyncClient]:
    """Same stack, but with the production wiring shape (a per-session factory)."""
    async with _api_client(policy_factory=_fake_policy_factory()) as client:
        yield client


async def _register_and_login(
    client: httpx.AsyncClient, email: str, password: str = "correct horse battery"
) -> str:
    """Register a fresh shopper and return its access token."""
    register_captcha = (await client.get("/api/v1/auth/captcha")).json()["data"]
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "captcha_token": register_captcha["captcha_token"],
            "captcha_answer": _solve(register_captcha["question"]),
        },
    )
    assert register.status_code == 201, register.text

    login_captcha = (await client.get("/api/v1/auth/captcha")).json()["data"]
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "captcha_token": login_captcha["captcha_token"],
            "captcha_answer": _solve(login_captcha["question"]),
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["data"]["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_register_login_and_me_flow(api_client: httpx.AsyncClient) -> None:
    email = f"user-{uuid4().hex[:12]}@example.invalid"
    token = await _register_and_login(api_client, email)

    me = await api_client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200
    body = me.json()["data"]
    assert body["email"] == email
    assert body["role"] == "shopper"
    assert "permissions" in body


async def test_conversation_and_chat_stream_flow(api_client: httpx.AsyncClient) -> None:
    email = f"user-{uuid4().hex[:12]}@example.invalid"
    token = await _register_and_login(api_client, email)

    created = await api_client.post(
        "/api/v1/conversations", json={"title": "测试会话"}, headers=_auth(token)
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["data"]["id"]

    payload = {
        "conversation_id": conversation_id,
        "message": "你好",
        "client_message_id": str(uuid4()),
    }
    async with api_client.stream(
        "POST", "/api/v1/chat/stream", json=payload, headers=_auth(token)
    ) as response:
        assert response.status_code == 200
        raw = (await response.aread()).decode("utf-8")

    assert "event: meta" in raw
    assert "event: delta" in raw
    assert "event: done" in raw

    messages = await api_client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=_auth(token)
    )
    assert messages.status_code == 200
    roles = [item["role"] for item in messages.json()["data"]["items"]]
    assert "user" in roles
    assert "assistant" in roles


async def test_cross_tenant_isolation(api_client: httpx.AsyncClient) -> None:
    token_a = await _register_and_login(api_client, f"a-{uuid4().hex[:12]}@example.invalid")
    token_b = await _register_and_login(api_client, f"b-{uuid4().hex[:12]}@example.invalid")

    created = await api_client.post(
        "/api/v1/conversations", json={"title": "A 的会话"}, headers=_auth(token_a)
    )
    conversation_id = created.json()["data"]["id"]

    # User B must see the same "not found" as a missing conversation.
    forbidden = await api_client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=_auth(token_b)
    )
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    # Renaming A's conversation as B must also fail as "not found".
    rename = await api_client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "越权重命名"},
        headers=_auth(token_b),
    )
    assert rename.status_code == 404


async def test_handoff_requires_idempotency_key(api_client: httpx.AsyncClient) -> None:
    email = f"user-{uuid4().hex[:12]}@example.invalid"
    token = await _register_and_login(api_client, email)

    created = await api_client.post("/api/v1/conversations", json={}, headers=_auth(token))
    conversation_id = created.json()["data"]["id"]

    body = {
        "conversation_id": conversation_id,
        "reason_code": "USER_REQUESTS_HUMAN",
        "summary_redacted": "转人工",
    }
    missing_key = await api_client.post("/api/v1/handoff", json=body, headers=_auth(token))
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "VALIDATION_ERROR"

    with_key = await api_client.post(
        "/api/v1/handoff",
        json=body,
        headers={**_auth(token), "Idempotency-Key": uuid4().hex},
    )
    assert with_key.status_code == 201, with_key.text
    assert with_key.json()["data"]["status"] == "open"


async def test_refresh_csrf_and_logout(api_client: httpx.AsyncClient) -> None:
    email = f"user-{uuid4().hex[:12]}@example.invalid"
    token = await _register_and_login(api_client, email)

    csrf = api_client.cookies.get("shopmate_csrf")

    # Without the CSRF header the refresh must be rejected.
    no_csrf = await api_client.post("/api/v1/auth/refresh")
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "CSRF_INVALID"

    # With the synchronizer token, refresh rotates and returns a usable access token.
    rotated = await api_client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200, rotated.text
    new_token = rotated.json()["data"]["access_token"]

    me = await api_client.get("/api/v1/auth/me", headers=_auth(new_token))
    assert me.status_code == 200

    # Logout revokes the refresh session; a later refresh has no valid cookie.
    await api_client.post("/api/v1/auth/logout", headers=_auth(token))
    assert api_client.cookies.get("shopmate_refresh") is None


async def test_policy_faq_streams_citation_events(api_client_with_policy) -> None:
    """A grounded policy answer must emit real citations, not a bare delta."""
    client = api_client_with_policy
    token = await _register_and_login(client, f"user-{uuid4().hex[:12]}@example.invalid")
    created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
    conversation_id = created.json()["data"]["id"]

    payload = {
        "conversation_id": conversation_id,
        "message": "七天无理由退货的政策是什么？",
        "client_message_id": str(uuid4()),
    }
    async with client.stream(
        "POST", "/api/v1/chat/stream", json=payload, headers=_auth(token)
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = (await response.aread()).decode("utf-8")

    events = _parse_sse(raw)
    types = [event["type"] for event in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    assert types.count("done") == 1
    assert events[0]["data"]["route"] == "policy_faq"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))

    citations = [event for event in events if event["type"] == "citation"]
    assert len(citations) == 1
    citation = citations[0]["data"]
    assert citation["citation_id"] == "cit_0000000000000001"
    assert citation["title"] == "退换货政策"
    assert citation["version"] == "2026.10.1"
    assert citation["page_no"] == 2
    assert citation["excerpt"]
    assert citation["as_of"] is not None

    assert any(event["type"] == "delta" for event in events)

    # Citations are persisted with the assistant message, not only streamed.
    messages = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=_auth(token)
    )
    assistant = [item for item in messages.json()["data"]["items"] if item["role"] == "assistant"]
    assert assistant[-1]["citations"], "assistant message must persist its citations"


async def test_chat_prefers_the_wired_policy_factory(api_client_with_policy_factory) -> None:
    """``POST /chat/stream`` must use ``policy_factory`` (the production wiring shape)."""
    client = api_client_with_policy_factory
    token = await _register_and_login(client, f"user-{uuid4().hex[:12]}@example.invalid")
    created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
    conversation_id = created.json()["data"]["id"]

    payload = {
        "conversation_id": conversation_id,
        "message": "七天无理由退货的政策是什么？",
        "client_message_id": str(uuid4()),
    }
    async with client.stream(
        "POST", "/api/v1/chat/stream", json=payload, headers=_auth(token)
    ) as response:
        raw = (await response.aread()).decode("utf-8")

    events = _parse_sse(raw)
    types = [event["type"] for event in events]
    assert types[0] == "meta"
    assert types[-1] == "done"
    # The factory-provided service answered, so a real citation reached the client.
    assert "citation" in types


async def test_tool_failure_emits_one_terminal_error_event(api_client) -> None:
    """A failing tool must terminate the stream with a single ``error`` and no ``done``."""
    client = api_client
    token = await _register_and_login(client, f"user-{uuid4().hex[:12]}@example.invalid")
    created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
    conversation_id = created.json()["data"]["id"]

    payload = {
        "conversation_id": conversation_id,
        "message": "帮我推荐一款降噪耳机",
        "client_message_id": str(uuid4()),
    }
    failure = ToolFailure(
        tool_call_id=uuid4(),
        error_code=ErrorCode.UPSTREAM_UNAVAILABLE.value,
        user_message="上游暂不可用，请稍后重试。",
        retryable=True,
        retry_after_ms=3000,
        trace_id=uuid4(),
    )
    with patch.object(ToolDispatcher, "invoke", new=AsyncMock(return_value=failure)):
        async with client.stream(
            "POST", "/api/v1/chat/stream", json=payload, headers=_auth(token)
        ) as response:
            assert response.status_code == 200
            raw = (await response.aread()).decode("utf-8")

    events = _parse_sse(raw)
    types = [event["type"] for event in events]
    assert types[0] == "meta"
    assert types[-1] == "error"
    assert types.count("error") == 1
    assert "done" not in types
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))

    error = events[-1]["data"]
    assert error["error_code"] == "UPSTREAM_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["retry_after_ms"] == 3000
    # The snapshot is persisted once as incomplete, so history shows "未完成" (7.9/7.10).
    assert error["partial_persisted"] is True
    assert error["partial_message_id"] is not None

    messages = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=_auth(token)
    )
    assistant = [item for item in messages.json()["data"]["items"] if item["role"] == "assistant"]
    assert assistant[-1]["id"] == error["partial_message_id"]
    assert assistant[-1]["is_complete"] is False
    assert assistant[-1]["finish_reason"] == "error"


async def test_handoff_idempotent_replay_and_conflict(api_client) -> None:
    """Same key replays the same ticket; same key with a different payload conflicts."""
    client = api_client
    token = await _register_and_login(client, f"user-{uuid4().hex[:12]}@example.invalid")
    created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
    conversation_id = created.json()["data"]["id"]
    body = {
        "conversation_id": conversation_id,
        "reason_code": "USER_REQUESTS_HUMAN",
        "summary_redacted": "用户要求转人工",
    }
    key = f"handoff-{uuid4().hex}"

    first = await client.post(
        "/api/v1/handoff", json=body, headers={**_auth(token), "Idempotency-Key": key}
    )
    assert first.status_code == 201, first.text
    ticket_id = first.json()["data"]["ticket_id"]
    assert first.json()["data"]["idempotent_replay"] is False

    replay = await client.post(
        "/api/v1/handoff", json=body, headers={**_auth(token), "Idempotency-Key": key}
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["data"]["ticket_id"] == ticket_id
    assert replay.json()["data"]["idempotent_replay"] is True

    listing = await client.get("/api/v1/handoff", headers=_auth(token))
    tickets = listing.json()["data"]["items"]
    assert len([item for item in tickets if item["ticket_id"] == ticket_id]) == 1

    conflict = await client.post(
        "/api/v1/handoff",
        json={**body, "summary_redacted": "与首次请求不同的摘要"},
        headers={**_auth(token), "Idempotency-Key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict.json()["error"]["retryable"] is False

    # Another user must not see (or enumerate) this ticket.
    other_token = await _register_and_login(client, f"other-{uuid4().hex[:12]}@example.invalid")
    forbidden = await client.get(f"/api/v1/handoff/{ticket_id}", headers=_auth(other_token))
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
