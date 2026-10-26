"""Support workbench + admin write endpoints (stage 16, docs/06-api.md §12/§13).

The suite runs against PostgreSQL through the real ASGI app. Each test creates a private
shop (shopper, two support agents in different shops, an admin, a conversation with an
assistant answer containing PII, a tool-call summary and an ``open`` ticket) and deletes
every row afterwards, so the shared demo database keeps its seed counts.

What is proven here, endpoint by endpoint:

* ``GET /support/tickets`` returns exactly the 12 contract fields, risk-ordered;
* a shopper, an admin without ``support:*`` and an anonymous caller are all rejected;
* another shop's ticket is indistinguishable from a missing one;
* ``PATCH`` enforces the state machine (``409 INVALID_STATE``) and cross-shop assignee
  (``403``) and writes an ``audit_events`` row per transition;
* a transcript needs an authorising ticket, and the PII in it never comes back raw;
* quality labels are scoped to an authorised assistant message and are idempotent
  per agent;
* ``POST /admin/documents`` stores a real Markdown file, returns ``202`` + ``pending`` and
  the document shows up in the admin list with a queued ingestion job;
* ``PATCH``/``DELETE`` on a chunk recompute the hash and demand a reindex.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    issue_access_token,
    permissions_for,
)
from shopmate_ecommerce_assistant.db.models import (
    AuditEvent,
    Conversation,
    HandoffStatus,
    HandoffTicket,
    IngestionJob,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Message,
    MessageRole,
    Shop,
    SupportQualityLabel,
    ToolCall,
    ToolCallStatus,
    User,
    UserRole,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app
from shopmate_ecommerce_assistant.safety.risk import RiskLevel

pytestmark = pytest.mark.integration

SENSITIVE_PHONE = "13800138000"

CONTRACT_FIELDS = {
    "ticket_id",
    "status",
    "risk_level",
    "primary_reason_code",
    "reason_codes",
    "priority",
    "queue",
    "conversation_id",
    "user_reference_masked",
    "assigned_to_masked",
    "created_at",
    "waiting_seconds",
    # stage-20 fix: the workbench must be able to tell that a ticket's transcript is gone
    "transcript_available",
}


@dataclass(frozen=True, slots=True)
class Fixture:
    client: httpx.AsyncClient
    settings: Settings
    shop_id: UUID
    other_shop_id: UUID
    shopper: UUID
    support: UUID
    other_support: UUID
    admin: UUID
    conversation_id: UUID
    ticket_id: UUID
    assistant_message_id: UUID
    user_message_id: UUID
    chunk_id: UUID
    document_id: UUID
    version_id: UUID

    def token(
        self,
        user_id: UUID,
        role: UserRole = UserRole.SUPPORT,
        *,
        shop_id: UUID | None = None,
    ) -> str:
        context = AccessContext(
            shop_id=shop_id or self.shop_id,
            user_id=user_id,
            role=role,
            permissions=permissions_for(role),
        )
        return issue_access_token(self.settings, context)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user(shop_id: UUID, email: str, role: UserRole) -> User:
    return User(
        id=uuid4(),
        shop_id=shop_id,
        email_ci=email,
        password_hash="!synthetic-account-no-login",
        display_name_masked=email.split("@")[0][:2] + "****",
        role=role,
    )


async def _seed(session) -> dict[str, object]:
    now = datetime.now(UTC)
    shop = Shop(id=uuid4(), name="阶段16 客服测试店铺")
    other_shop = Shop(id=uuid4(), name="阶段16 跨店测试店铺")

    shopper = _user(shop.id, "support-shopper@example.invalid", UserRole.SHOPPER)
    support = _user(shop.id, "support-agent@example.invalid", UserRole.SUPPORT)
    other_support = _user(other_shop.id, "support-other@example.invalid", UserRole.SUPPORT)
    admin = _user(shop.id, "support-admin@example.invalid", UserRole.ADMIN)

    conversation = Conversation(
        id=uuid4(), shop_id=shop.id, user_id=shopper.id, title="订单售后咨询"
    )
    user_message = Message(
        id=uuid4(),
        shop_id=shop.id,
        conversation_id=conversation.id,
        user_id=shopper.id,
        role=MessageRole.USER,
        content="我的手机号 13800138000，订单还没到。",
        created_at=now - timedelta(minutes=2),
    )
    assistant_message = Message(
        id=uuid4(),
        shop_id=shop.id,
        conversation_id=conversation.id,
        user_id=shopper.id,
        role=MessageRole.ASSISTANT,
        content=f"已记录您的手机号 {SENSITIVE_PHONE}，客服会尽快联系您。",
        citations_jsonb=[{"document_id": str(uuid4()), "label": "c1"}],
        risk_jsonb={"level": "high", "rule_codes": ["COMPLAINT"]},
        route="complaint_handoff",
        created_at=now - timedelta(minutes=1),
    )
    tool_call = ToolCall(
        id=uuid4(),
        request_id=uuid4(),
        trace_id=uuid4(),
        shop_id=shop.id,
        conversation_id=conversation.id,
        user_id=shopper.id,
        actor_user_id=shopper.id,
        tool_name="get_order_status",
        input_redacted_jsonb={"order_no": "SUP-****0001"},
        result_summary_jsonb={"status": "shipped"},
        status=ToolCallStatus.SUCCEEDED,
        latency_ms=120,
    )
    ticket = HandoffTicket(
        id=uuid4(),
        shop_id=shop.id,
        conversation_id=conversation.id,
        user_id=shopper.id,
        risk_level=RiskLevel.HIGH,
        primary_reason_code="COMPLAINT",
        risk_rule_codes_jsonb=["COMPLAINT", "MONEY_DECISION_REQUIRED"],
        summary_redacted="用户投诉并要求赔偿（合成）",
        status=HandoffStatus.OPEN,
        priority=2,
        created_at=now - timedelta(seconds=120),
    )

    knowledge_base = KnowledgeBase(
        id=uuid4(), shop_id=shop.id, name="阶段16 测试知识库", locale="zh-CN", region="CN"
    )
    document = KnowledgeDocument(
        id=uuid4(),
        shop_id=shop.id,
        knowledge_base_id=knowledge_base.id,
        title="阶段16 测试政策",
        doc_type="policy",
        locale="zh-CN",
        region="CN",
    )
    version = KnowledgeVersion(
        id=uuid4(),
        shop_id=shop.id,
        document_id=document.id,
        version="1",
        source_uri="policy/stage16-test.md",
        source_filename="stage16-test.md",
        mime_type="text/markdown",
        content_hash=b"\x00" * 32,
        effective_from=now - timedelta(days=1),
        effective_to=None,
        parse_status="ready",
    )
    chunk = KnowledgeChunk(
        id=uuid4(),
        shop_id=shop.id,
        knowledge_base_id=knowledge_base.id,
        document_id=document.id,
        version_id=version.id,
        chunk_index=0,
        heading_path=["测试"],
        text="原始片段文本",
        content_hash=b"\x01" * 32,
        token_count=6,
        is_enabled=True,
        metadata_jsonb={"role": "child"},
    )

    # Explicit staging: the composite FKs (document -> version -> chunk) are declared
    # without ORM relationships, so insert order is made explicit instead of relying on
    # the unit-of-work sorter.
    session.add_all(
        [
            shop,
            other_shop,
            shopper,
            support,
            other_support,
            admin,
            conversation,
            user_message,
            assistant_message,
            tool_call,
            ticket,
            knowledge_base,
            document,
        ]
    )
    await session.commit()
    session.add(version)
    await session.commit()
    session.add(chunk)
    await session.execute(
        sa.update(KnowledgeDocument)
        .where(KnowledgeDocument.id == document.id)
        .values(current_version_id=version.id)
    )
    await session.commit()
    return {
        "shop": shop,
        "other_shop": other_shop,
        "shopper": shopper,
        "support": support,
        "other_support": other_support,
        "admin": admin,
        "conversation": conversation,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "ticket": ticket,
        "chunk": chunk,
        "document": document,
        "version": version,
    }


async def _cleanup(session, shop_ids: tuple[UUID, ...]) -> None:
    for shop_id in shop_ids:
        for model in (
            SupportQualityLabel,
            AuditEvent,
            IngestionJob,
            KnowledgeChunk,
            KnowledgeVersion,
            KnowledgeDocument,
            KnowledgeBase,
            ToolCall,
            HandoffTicket,
            Message,
            Conversation,
            User,
        ):
            await session.execute(sa.delete(model).where(model.shop_id == shop_id))
        await session.execute(sa.delete(Shop).where(Shop.id == shop_id))
    await session.commit()


@asynccontextmanager
async def _fixture() -> AsyncIterator[Fixture]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用：跳过客服工作台集成测试")

    factory = create_session_factory(engine)
    async with factory() as session:
        data = await _seed(session)

    shop_id = data["shop"].id
    other_shop_id = data["other_shop"].id

    app = create_app(settings)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.policy = None
    app.state.policy_factory = None
    # CI must not load BGE-M3: the upload endpoint then leaves the job queued, which is
    # exactly the state a worker-less deployment shows.
    app.state.ingestion_runner = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Fixture(
            client=client,
            settings=settings,
            shop_id=shop_id,
            other_shop_id=other_shop_id,
            shopper=data["shopper"].id,
            support=data["support"].id,
            other_support=data["other_support"].id,
            admin=data["admin"].id,
            conversation_id=data["conversation"].id,
            ticket_id=data["ticket"].id,
            assistant_message_id=data["assistant_message"].id,
            user_message_id=data["user_message"].id,
            chunk_id=data["chunk"].id,
            document_id=data["document"].id,
            version_id=data["version"].id,
        )

    uploads = Path(paths.KNOWLEDGE_DIR) / "uploads" / str(shop_id)
    if uploads.exists():
        shutil.rmtree(uploads, ignore_errors=True)
    async with factory() as session:
        await _cleanup(session, (shop_id, other_shop_id))
    await engine.dispose()


@pytest.fixture
async def fx() -> AsyncIterator[Fixture]:
    async with _fixture() as fixture:
        yield fixture


# --------------------------------------------------------------------------- 工单队列


async def test_queue_returns_exactly_the_contract_fields(fx: Fixture) -> None:
    """§12: the list item carries the 12 fixed fields and no internal ones."""
    response = await fx.client.get("/api/v1/support/tickets", headers=_auth(fx.token(fx.support)))
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert set(item) == CONTRACT_FIELDS
    assert item["ticket_id"] == str(fx.ticket_id)
    assert item["queue"] == "priority_support"
    assert item["risk_level"] == "high"
    assert item["reason_codes"] == ["COMPLAINT", "MONEY_DECISION_REQUIRED"]
    assert item["assigned_to_masked"] is None
    assert item["waiting_seconds"] >= 100
    assert "support-shopper" not in item["user_reference_masked"]


async def test_queue_hides_tickets_whose_transcript_is_gone(fx: Fixture) -> None:
    """默认队列只保留能取证的行；会话软删后仍可用 transcript=all 翻出来并标注。"""
    headers = _auth(fx.token(fx.support))

    before = await fx.client.get("/api/v1/support/tickets", headers=headers)
    assert len(before.json()["data"]["items"]) == 1
    assert before.json()["data"]["items"][0]["transcript_available"] is True

    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        await session.execute(
            sa.update(Conversation)
            .where(Conversation.id == fx.conversation_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await session.commit()
    await engine.dispose()

    default_view = await fx.client.get("/api/v1/support/tickets", headers=headers)
    assert default_view.json()["data"]["items"] == []

    everything = await fx.client.get(
        "/api/v1/support/tickets", params={"transcript": "all"}, headers=headers
    )
    items = everything.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["transcript_available"] is False

    bad = await fx.client.get(
        "/api/v1/support/tickets", params={"transcript": "nonsense"}, headers=headers
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_deleted_conversation_says_why_it_is_unavailable(fx: Fixture) -> None:
    """取证失败要说明原因，不能对所有情况都回同一句「未找到该会话」。"""
    headers = _auth(fx.token(fx.support))
    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        await session.execute(
            sa.update(Conversation)
            .where(Conversation.id == fx.conversation_id)
            .values(deleted_at=datetime.now(UTC))
        )
        await session.commit()
    await engine.dispose()

    response = await fx.client.get(
        f"/api/v1/support/conversations/{fx.conversation_id}", headers=headers
    )
    assert response.status_code == 404
    assert "已被用户删除" in response.json()["error"]["message"]


async def test_consumer_admin_and_anonymous_are_rejected(fx: Fixture) -> None:
    """§12: shoppers have no ticket permission and admin does not get it by default."""
    shopper = await fx.client.get(
        "/api/v1/support/tickets", headers=_auth(fx.token(fx.shopper, UserRole.SHOPPER))
    )
    assert shopper.status_code == 403
    assert shopper.json()["error"]["code"] == "FORBIDDEN"

    admin = await fx.client.get(
        "/api/v1/support/tickets", headers=_auth(fx.token(fx.admin, UserRole.ADMIN))
    )
    assert admin.status_code == 403, "admin must not inherit support:ticket:read"

    anonymous = await fx.client.get("/api/v1/support/tickets")
    assert anonymous.status_code == 401


async def test_other_shop_ticket_is_indistinguishable_from_missing(fx: Fixture) -> None:
    foreign = await fx.client.get(
        f"/api/v1/support/tickets/{fx.ticket_id}",
        headers=_auth(fx.token(fx.other_support, shop_id=fx.other_shop_id)),
    )
    missing = await fx.client.get(
        f"/api/v1/support/tickets/{uuid4()}",
        headers=_auth(fx.token(fx.other_support, shop_id=fx.other_shop_id)),
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"] == missing.json()["error"]


async def test_ticket_detail_matches_contract(fx: Fixture) -> None:
    response = await fx.client.get(
        f"/api/v1/support/tickets/{fx.ticket_id}", headers=_auth(fx.token(fx.support))
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == CONTRACT_FIELDS | {"updated_at", "summary_redacted", "expected_response"}
    assert data["summary_redacted"] == "用户投诉并要求赔偿（合成）"
    assert data["expected_response"]


# ------------------------------------------------------------------- 状态机与审计


async def test_archive_closes_a_ticket_without_a_transcript(fx: Fixture) -> None:
    """archive：open/assigned/resolved 可直接归档，原因必填，并留下审计。"""
    headers = _auth(fx.token(fx.support))
    url = f"/api/v1/support/tickets/{fx.ticket_id}"

    without_reason = await fx.client.patch(url, json={"action": "archive"}, headers=headers)
    assert without_reason.status_code == 400
    assert without_reason.json()["error"]["code"] == "VALIDATION_ERROR"

    with_summary = await fx.client.patch(
        url, json={"action": "archive", "resolution_summary": "不支持"}, headers=headers
    )
    assert with_summary.status_code == 400

    archived = await fx.client.patch(
        url, json={"action": "archive", "close_reason": "会话已被用户删除"}, headers=headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["status"] == "closed"

    again = await fx.client.patch(
        url, json={"action": "archive", "close_reason": "再来一次"}, headers=headers
    )
    assert again.status_code == 409

    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        actions = (
            await session.execute(
                sa.select(AuditEvent.action).where(
                    AuditEvent.shop_id == fx.shop_id, AuditEvent.resource_id == fx.ticket_id
                )
            )
        ).scalars()
        assert "support.ticket.archive" in set(actions)
        reason = (
            await session.execute(
                sa.select(HandoffTicket.close_reason).where(HandoffTicket.id == fx.ticket_id)
            )
        ).scalar_one()
        assert reason == "会话已被用户删除"
    await engine.dispose()


async def test_state_machine_and_audit(fx: Fixture) -> None:
    """assign -> resolve -> close, with ``409`` on an illegal jump and one audit per move."""
    headers = _auth(fx.token(fx.support))
    url = f"/api/v1/support/tickets/{fx.ticket_id}"

    # resolve from open is illegal
    illegal = await fx.client.patch(
        url, json={"action": "resolve", "resolution_summary": "已处理"}, headers=headers
    )
    assert illegal.status_code == 409, illegal.text
    assert illegal.json()["error"]["code"] == "INVALID_STATE"

    assigned = await fx.client.patch(url, json={"action": "assign"}, headers=headers)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["status"] == "assigned"
    assert assigned.json()["data"]["assigned_to_masked"] is not None

    # resolve without a summary is a validation error, not a silent success
    missing_summary = await fx.client.patch(url, json={"action": "resolve"}, headers=headers)
    assert missing_summary.status_code == 400
    assert missing_summary.json()["error"]["code"] == "VALIDATION_ERROR"

    resolved = await fx.client.patch(
        url, json={"action": "resolve", "resolution_summary": "已解释政策并登记"}, headers=headers
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["data"]["status"] == "resolved"

    closed = await fx.client.patch(
        url, json={"action": "close", "close_reason": "用户满意"}, headers=headers
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["status"] == "closed"

    again = await fx.client.patch(url, json={"action": "close"}, headers=headers)
    assert again.status_code == 409

    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        actions = (
            (
                await session.execute(
                    sa.select(AuditEvent.action).where(
                        AuditEvent.shop_id == fx.shop_id,
                        AuditEvent.resource_id == fx.ticket_id,
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert sorted(actions) == [
        "support.ticket.assign",
        "support.ticket.close",
        "support.ticket.resolve",
    ]


async def test_cross_shop_assignee_is_forbidden(fx: Fixture) -> None:
    """§12: an assignee must be a support/admin of the caller's own shop."""
    response = await fx.client.patch(
        f"/api/v1/support/tickets/{fx.ticket_id}",
        json={"action": "assign", "assignee_user_id": str(fx.other_support)},
        headers=_auth(fx.token(fx.support)),
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --------------------------------------------------------------------- 会话取证


async def test_conversation_requires_authorising_ticket_and_masks_pii(fx: Fixture) -> None:
    headers = _auth(fx.token(fx.support))
    ok = await fx.client.get(f"/api/v1/support/conversations/{fx.conversation_id}", headers=headers)
    assert ok.status_code == 200, ok.text
    data = ok.json()["data"]
    assert data["target_user_id"] == str(fx.shopper)
    assert data["ticket_id"] == str(fx.ticket_id)
    assert data["handoff"]["primary_reason_code"] == "COMPLAINT"
    assert [message["role"] for message in data["messages"]] == ["user", "assistant"]
    assert all(SENSITIVE_PHONE not in message["content"] for message in data["messages"])
    assert data["messages"][1]["risk"]["rule_codes"] == ["COMPLAINT"]
    assert data["tool_calls"][0]["tool_name"] == "get_order_status"

    unrelated = await fx.client.get(f"/api/v1/support/conversations/{uuid4()}", headers=headers)
    assert unrelated.status_code == 404


async def test_conversation_requires_conversation_permission(fx: Fixture) -> None:
    admin = await fx.client.get(
        f"/api/v1/support/conversations/{fx.conversation_id}",
        headers=_auth(fx.token(fx.admin, UserRole.ADMIN)),
    )
    assert admin.status_code == 403, "admin must not browse consumer transcripts by default"


# -------------------------------------------------------------------- 质量标记


async def test_quality_label_is_owned_and_idempotent(fx: Fixture) -> None:
    headers = _auth(fx.token(fx.support))
    url = f"/api/v1/support/messages/{fx.assistant_message_id}/quality-labels"

    created = await fx.client.post(
        url,
        json={"label": "needs_knowledge", "reason_summary": "片段未覆盖配送地区"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["label"] == "needs_knowledge"

    updated = await fx.client.post(url, json={"label": "incorrect"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["label"] == "incorrect"

    user_message = await fx.client.post(
        f"/api/v1/support/messages/{fx.user_message_id}/quality-labels",
        json={"label": "correct"},
        headers=headers,
    )
    assert user_message.status_code == 404, "only assistant messages can be labelled"

    other_shop = await fx.client.post(
        url,
        json={"label": "correct"},
        headers=_auth(fx.token(fx.other_support, shop_id=fx.other_shop_id)),
    )
    assert other_shop.status_code == 404

    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    sa.select(SupportQualityLabel.label).where(
                        SupportQualityLabel.message_id == fx.assistant_message_id
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert list(rows) == ["incorrect"], "one agent keeps one current verdict"


# ------------------------------------------------------------------ 管理端写入


async def test_upload_creates_pending_version_and_queued_job(fx: Fixture) -> None:
    headers = _auth(fx.token(fx.admin, UserRole.ADMIN))
    knowledge_bases = await fx.client.get("/api/v1/admin/knowledge-bases", headers=headers)
    kb_id = next(
        item["id"]
        for item in knowledge_bases.json()["data"]["items"]
        if item["name"] == "阶段16 测试知识库"
    )

    body = "# 测试政策\n\n退货期限为七天。\n".encode()
    response = await fx.client.post(
        "/api/v1/admin/documents",
        data={
            "knowledge_base_id": kb_id,
            "title": "阶段16 上传测试",
            "doc_type": "policy",
            "locale": "zh-CN",
            "region": "CN",
            "effective_from": "2026-10-01T00:00:00Z",
        },
        files={"file": ("stage16-upload.md", body, "text/markdown")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["parse_status"] == "pending"

    documents = await fx.client.get("/api/v1/admin/documents", headers=headers)
    listed = {item["document_id"]: item for item in documents.json()["data"]["items"]}
    assert data["document_id"] in listed
    assert listed[data["document_id"]]["parse_status"] == "pending"

    engine = create_engine(fx.settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        job_status = await session.scalar(
            sa.select(IngestionJob.status).where(IngestionJob.id == UUID(data["ingestion_job_id"]))
        )
    await engine.dispose()
    assert str(job_status) == "queued", "no worker in CI, so the job must stay queued"

    reindex = await fx.client.post(
        f"/api/v1/admin/documents/{data['document_id']}/reindex", headers=headers
    )
    assert reindex.status_code == 202, reindex.text
    assert reindex.json()["data"]["status"] == "queued"
    assert reindex.json()["data"]["ingestion_job_id"] != data["ingestion_job_id"]


async def test_upload_rejects_wrong_magic_and_unsafe_name(fx: Fixture) -> None:
    headers = _auth(fx.token(fx.admin, UserRole.ADMIN))
    knowledge_bases = await fx.client.get("/api/v1/admin/knowledge-bases", headers=headers)
    kb_id = next(
        item["id"]
        for item in knowledge_bases.json()["data"]["items"]
        if item["name"] == "阶段16 测试知识库"
    )
    form = {
        "knowledge_base_id": kb_id,
        "title": "阶段16 拒绝测试",
        "doc_type": "policy",
        "locale": "zh-CN",
        "region": "CN",
        "effective_from": "2026-10-01T00:00:00Z",
    }

    # a .pdf whose bytes are plain text: magic check must refuse it
    fake_pdf = await fx.client.post(
        "/api/v1/admin/documents",
        data=form,
        files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")},
        headers=headers,
    )
    assert fake_pdf.status_code == 415, fake_pdf.text
    assert fake_pdf.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    traversal = await fx.client.post(
        "/api/v1/admin/documents",
        data=form,
        files={"file": ("../escape.md", b"# x\n", "text/markdown")},
        headers=headers,
    )
    assert traversal.status_code == 400
    assert traversal.json()["error"]["code"] == "UNSAFE_FILE"


async def test_chunk_edit_requires_reindex(fx: Fixture) -> None:
    headers = _auth(fx.token(fx.admin, UserRole.ADMIN))
    url = f"/api/v1/admin/chunks/{fx.chunk_id}"

    patched = await fx.client.patch(
        url, json={"text": "修正后的知识单元文本", "change_reason": "修正章节措辞"}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    data = patched.json()["data"]
    assert data["reindex_required"] is True
    assert data["text"] == "修正后的知识单元文本"
    assert data["content_hash"] != "01" * 32

    deleted = await fx.client.delete(url, headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["is_enabled"] is False
    assert deleted.json()["data"]["reindex_required"] is True

    missing = await fx.client.patch(url, json={"text": "再改一次"}, headers=headers)
    assert missing.status_code == 400


async def test_admin_writes_require_admin_role(fx: Fixture) -> None:
    shopper = await fx.client.patch(
        f"/api/v1/admin/chunks/{fx.chunk_id}",
        json={"text": "越权修改"},
        headers=_auth(fx.token(fx.shopper, UserRole.SHOPPER)),
    )
    assert shopper.status_code == 403
    support = await fx.client.get("/api/v1/admin/documents", headers=_auth(fx.token(fx.support)))
    assert support.status_code == 403
