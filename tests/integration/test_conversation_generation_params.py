"""Conversation-scoped generation parameters over the real API (stage 19).

Covers the contract in ``docs/06-api.md`` §6.1:

* a conversation remembers temperature / top_p / max_tokens / history_turns overrides
  (merge semantics: omitted keeps, explicit ``null`` clears, all-``null`` restores defaults);
* an out-of-range value — or a ``max_tokens`` above the operator cap — is rejected as a
  whole request and nothing is persisted;
* ``POST /chat/stream`` resolves the stored overrides server-side and the SSE stream is
  unaffected (the same event sequence as without overrides).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.generation import DEFAULT_HISTORY_TURNS, GenerationParams
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app

pytestmark = pytest.mark.integration

_CAPTCHA_RE = re.compile(r"(\d+)\s*\+\s*(\d+)\s*=\s*\?")


def _solve(question: str) -> str:
    match = _CAPTCHA_RE.search(question)
    assert match, f"无法解析验证码题目：{question}"
    return str(int(match.group(1)) + int(match.group(2)))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _ScopedPolicy:
    """Records the scope and generation parameters it was called with."""

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


async def _login(client: httpx.AsyncClient) -> str:
    """Register a fresh shopper and return its access token."""
    email = f"gen-{uuid4().hex[:12]}@example.invalid"
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
    return login.json()["data"]["access_token"]


async def _conversation(client: httpx.AsyncClient, token: str) -> str:
    created = await client.post("/api/v1/conversations", json={}, headers=_auth(token))
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _sse_events(raw: str) -> list[dict]:
    events = []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


async def _patch_params(client: httpx.AsyncClient, token: str, conversation_id: str, body: dict):
    return await client.patch(
        f"/api/v1/conversations/{conversation_id}/generation-params",
        json=body,
        headers=_auth(token),
    )


async def test_patch_persists_merges_and_clears_overrides() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token = await _login(client)
        conversation_id = await _conversation(client, token)

        # A fresh conversation overrides nothing.
        fresh = await client.get("/api/v1/conversations", headers=_auth(token))
        item = next(i for i in fresh.json()["data"]["items"] if i["id"] == conversation_id)
        assert item["generation_params"] == {
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "history_turns": None,
        }

        first = await _patch_params(
            client, token, conversation_id, {"temperature": 0.7, "history_turns": 4}
        )
        assert first.status_code == 200, first.text
        assert first.json()["data"]["generation_params"]["temperature"] == 0.7
        assert first.json()["data"]["generation_params"]["history_turns"] == 4

        # Merge: an omitted field keeps its stored value.
        merged = await _patch_params(client, token, conversation_id, {"max_tokens": 1024})
        params = merged.json()["data"]["generation_params"]
        assert params["temperature"] == 0.7
        assert params["history_turns"] == 4
        assert params["max_tokens"] == 1024

        # An explicit null clears exactly that override.
        cleared = await _patch_params(client, token, conversation_id, {"temperature": None})
        params = cleared.json()["data"]["generation_params"]
        assert params["temperature"] is None
        assert params["history_turns"] == 4
        assert params["max_tokens"] == 1024

        # Idempotent re-read: the list endpoint returns the stored overrides.
        listed = await client.get("/api/v1/conversations", headers=_auth(token))
        item = next(i for i in listed.json()["data"]["items"] if i["id"] == conversation_id)
        assert item["generation_params"]["max_tokens"] == 1024

        # All-null restores the environment defaults.
        reset = await _patch_params(
            client,
            token,
            conversation_id,
            {"temperature": None, "top_p": None, "max_tokens": None, "history_turns": None},
        )
        assert reset.json()["data"]["generation_params"] == {
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "history_turns": None,
        }


async def test_out_of_range_parameters_are_rejected_and_nothing_is_persisted() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token = await _login(client)
        conversation_id = await _conversation(client, token)

        for bad in (
            {"temperature": 1.5},
            {"temperature": -0.01},
            {"top_p": 2.0},
            {"max_tokens": 0},
            {"max_tokens": -1},
            {"history_turns": -1},
            {"history_turns": 11},
        ):
            response = await _patch_params(client, token, conversation_id, bad)
            assert response.status_code == 400, (bad, response.text)
            assert response.json()["error"]["code"] == "VALIDATION_ERROR", bad

        # The operator cap is enforced on the write path (rejected, not clamped), with a
        # message that names the ceiling.
        cap = get_settings().llm_max_tokens_cap
        above = min(cap + 1, 8192)
        capped = await _patch_params(client, token, conversation_id, {"max_tokens": above})
        assert capped.status_code == 400, capped.text
        assert capped.json()["error"]["code"] == "VALIDATION_ERROR"
        if above > cap:
            assert str(cap) in capped.json()["error"]["message"]

        # A rejected request must not persist a partial override.
        listed = await client.get("/api/v1/conversations", headers=_auth(token))
        item = next(i for i in listed.json()["data"]["items"] if i["id"] == conversation_id)
        assert item["generation_params"] == {
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "history_turns": None,
        }


async def test_another_users_conversation_is_not_found() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        owner_token = await _login(client)
        intruder_token = await _login(client)
        conversation_id = await _conversation(client, owner_token)

        response = await _patch_params(
            client, intruder_token, conversation_id, {"temperature": 0.5}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


async def test_chat_stream_resolves_the_stored_parameters() -> None:
    """The stream reads the overrides server-side and the SSE sequence is untouched."""
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        token = await _login(client)
        conversation_id = await _conversation(client, token)

        patched = await _patch_params(
            client,
            token,
            conversation_id,
            {"temperature": 0.7, "top_p": 0.9, "max_tokens": 512, "history_turns": 0},
        )
        assert patched.status_code == 200, patched.text

        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "conversation_id": conversation_id,
                "message": "退货政策是怎么规定的？",
                "client_message_id": str(uuid4()),
            },
            headers=_auth(token),
        ) as response:
            assert response.status_code == 200
            raw = (await response.aread()).decode("utf-8")

        events = _sse_events(raw)
        types = [event["type"] for event in events]
        assert types[0] == "meta"
        assert types[-1] == "done"
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        # The stub policy answers without citations, so the event set is exactly the
        # pre-stage-19 one: the parameters change the LLM payload, never the protocol.
        assert types == ["meta", "delta", "done"]

        assert policy.generations, "the policy service should have been called"
        assert policy.generations[-1] == GenerationParams(
            temperature=0.7, top_p=0.9, max_tokens=512, history_turns=0
        )

        # Clearing the overrides restores the environment defaults for the next turn.
        await _patch_params(
            client,
            token,
            conversation_id,
            {"temperature": None, "top_p": None, "max_tokens": None, "history_turns": None},
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
        assert policy.generations[-1] == GenerationParams(history_turns=DEFAULT_HISTORY_TURNS)


async def test_generation_defaults_endpoint_reports_the_environment() -> None:
    policy = _ScopedPolicy()
    async with _client(policy) as client:
        anonymous = await client.get("/api/v1/generation-defaults")
        assert anonymous.status_code == 401

        token = await _login(client)
        response = await client.get("/api/v1/generation-defaults", headers=_auth(token))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        settings = get_settings()
        assert data["temperature"] == settings.llm_temperature
        assert data["history_turns"] == DEFAULT_HISTORY_TURNS
        assert data["max_tokens_cap"] == settings.llm_max_tokens_cap
        assert data["max_tokens"] == (settings.llm_max_tokens or None)
        assert data["top_p"] is None
