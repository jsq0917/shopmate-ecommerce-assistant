"""Image documents: OCR ingestion, metadata and the original-file endpoint (stage 20).

Covers the contract in ``docs/06-api.md`` §6.1 / §6.3:

* an OCR'd screenshot lands in PostgreSQL and Milvus like any text document;
* every chunk carries the picture's metadata (file name, pixel size, OCR statistics) plus
  a ``image_url`` that points at the authenticated asset endpoint;
* that endpoint serves the bytes to a caller of the same shop, and answers 404 for a
  document outside the caller's shop or for a non-image document.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.api.knowledge_assets import IMAGE_MIME_TYPES
from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter
from shopmate_ecommerce_assistant.db.models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeVersion,
    Shop,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app
from shopmate_ecommerce_assistant.rag.errors import VectorStoreUnavailable
from shopmate_ecommerce_assistant.rag.ingest import SourceSpec, ingest_source
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

pytestmark = pytest.mark.integration

SHOP_ID = stable_uuid("shop", "demo")
EMBEDDER = FakeHybridEmbeddingProvider()
KB_PREFIX = "test-image"

#: The committed fixture the seed renders; using the real file keeps the test independent
#: of the host's fonts (rendering happens once, in the repo).
CORPUS_IMAGE = paths.KNOWLEDGE_DIR / "policy" / "gift-card-screenshot-2026.10.1.png"

_Captcha = re.compile(r"(\d+)\s*\+\s*(\d+)\s*=\s*\?")


def _solve(question: str) -> str:
    match = _Captcha.search(question)
    assert match, f"无法解析验证码题目：{question}"
    return str(int(match.group(1)) + int(match.group(2)))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def store(settings: Settings) -> Iterator[MilvusKnowledgeStore | None]:
    instance = MilvusKnowledgeStore(settings)
    try:
        instance.ensure_collection()
    except VectorStoreUnavailable:  # pragma: no cover - environment dependent
        instance.close()
        pytest.skip("Milvus 不可用：跳过图片入库集成测试")
    yield instance
    instance.close()


def _require_corpus_image() -> None:
    if not CORPUS_IMAGE.is_file():
        pytest.skip("缺少图片语料，请先运行 scripts/seed.py 生成 data/knowledge")


async def test_screenshot_is_ingested_with_image_metadata(
    session, store: MilvusKnowledgeStore, settings: Settings, tmp_path: Path
) -> None:
    _require_corpus_image()
    (tmp_path / "policy").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CORPUS_IMAGE, tmp_path / "policy" / CORPUS_IMAGE.name)

    kb_name = f"{KB_PREFIX}-{uuid4().hex[:8]}"
    spec = SourceSpec(
        document_key=f"test-image-{uuid4().hex[:8]}",
        title="礼品卡使用说明（截图版）",
        doc_type="policy",
        version="2026.10.1",
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=None,
        locale="zh-CN",
        region="CN",
        knowledge_base=kb_name,
        file=f"policy/{CORPUS_IMAGE.name}",
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        outcome = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=tmp_path,
            shop_id=SHOP_ID,
        )
        version_ids.append(outcome.version_id)
        document_ids.append(outcome.document_id)
        assert outcome.ok, outcome.error_message
        assert outcome.child_count >= 1

        version = await session.get(KnowledgeVersion, outcome.version_id)
        assert version is not None
        assert version.mime_type == "image/png"

        chunks = (
            await session.scalars(
                sa.select(KnowledgeChunk).where(KnowledgeChunk.version_id == outcome.version_id)
            )
        ).all()
        assert chunks
        for chunk in chunks:
            image = chunk.metadata_jsonb["image"]
            assert image["filename"] == CORPUS_IMAGE.name
            assert image["width"] == 1080
            assert image["height"] > 0
            # The URL is document-scoped so a citation can link straight back to the file.
            assert image["image_url"] == f"/api/v1/knowledge-images/{outcome.document_id}"
            # OCR text is what got chunked; the title is not part of the picture text.
            assert "礼品卡" in chunk.text or "礼品卡" in "".join(
                item.text for item in chunks if item.text
            )

        child = next(chunk for chunk in chunks if chunk.is_enabled)
        assert "三十六个月内有效" in child.text
        assert child.page_no == 1
        assert list(child.heading_path) == []
    finally:
        for version_id in version_ids:
            store.delete_version(str(version_id))
        if version_ids:
            await session.execute(
                sa.delete(KnowledgeChunk).where(KnowledgeChunk.version_id.in_(version_ids))
            )
            await session.execute(
                sa.delete(IngestionJob).where(IngestionJob.version_id.in_(version_ids))
            )
            await session.execute(
                sa.delete(KnowledgeVersion).where(KnowledgeVersion.id.in_(version_ids))
            )
        for document_id in document_ids:
            await session.execute(
                sa.update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(current_version_id=None)
            )
            await session.execute(
                sa.delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
            )
        await session.execute(
            sa.delete(KnowledgeBase).where(KnowledgeBase.name.like(f"{KB_PREFIX}%"))
        )
        await session.commit()


# --- the original-file endpoint ----------------------------------------------------

_CREATED: list[tuple[UUID, UUID, UUID]] = []
_CREATED_SHOPS: list[UUID] = []


async def _insert_shop() -> UUID:
    """Create a throwaway shop so the cross-tenant 404 can be exercised for real."""
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    shop_id = uuid4()
    try:
        async with factory() as session:
            session.add(Shop(id=shop_id, name=f"{KB_PREFIX}-shop-{uuid4().hex[:6]}"))
            await session.commit()
    finally:
        await engine.dispose()
    _CREATED_SHOPS.append(shop_id)
    return shop_id


@asynccontextmanager
async def _client() -> AsyncIterator[httpx.AsyncClient]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("select 1"))
            await connection.execute(sa.text("select 1 from knowledge_versions limit 1"))
    except Exception:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用或未执行 alembic upgrade head：跳过")

    factory = create_session_factory(engine)
    app = create_app(settings)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.policy = None
    app.state.policy_factory = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def _login(client: httpx.AsyncClient) -> tuple[str, UUID]:
    email = f"img-{uuid4().hex[:12]}@example.invalid"
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


async def _insert_image_document(
    *, shop_id: UUID, source_uri: str, mime_type: str, suffix: str
) -> tuple[UUID, UUID]:
    """Create the three rows the endpoint reads, without running the ingest pipeline."""
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    kb_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    try:
        async with factory() as session:
            session.add(
                KnowledgeBase(
                    id=kb_id,
                    shop_id=shop_id,
                    name=f"{KB_PREFIX}-{uuid4().hex[:8]}",
                    locale="zh-CN",
                    region="CN",
                    status=KnowledgeBaseStatus.ACTIVE,
                )
            )
            await session.flush()
            # ``knowledge_documents`` and ``knowledge_versions`` reference each other, so the
            # document is inserted first without a current version and linked afterwards.
            session.add(
                KnowledgeDocument(
                    id=document_id,
                    shop_id=shop_id,
                    knowledge_base_id=kb_id,
                    title="礼品卡使用说明（截图版）",
                    doc_type="policy",
                    locale="zh-CN",
                    region="CN",
                    status=KnowledgeDocumentStatus.ACTIVE,
                )
            )
            await session.flush()
            session.add(
                KnowledgeVersion(
                    id=version_id,
                    shop_id=shop_id,
                    document_id=document_id,
                    version="2026.10.1",
                    source_uri=source_uri,
                    source_filename=f"{version_id.hex}{suffix}",
                    mime_type=mime_type,
                    content_hash=b"x" * 32,
                    effective_from=datetime(2026, 10, 1, tzinfo=UTC),
                )
            )
            await session.flush()
            await session.execute(
                sa.update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(current_version_id=version_id)
            )
            await session.commit()
    finally:
        await engine.dispose()
    _CREATED.append((document_id, version_id, kb_id))
    return document_id, version_id


@pytest.fixture(scope="module", autouse=True)
async def _cleanup_created_rows() -> AsyncIterator[None]:
    yield
    if not _CREATED:
        return
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    document_ids = [document_id for document_id, _, _ in _CREATED]
    version_ids = [version_id for _, version_id, _ in _CREATED]
    kb_ids = [kb_id for _, _, kb_id in _CREATED]
    try:
        async with factory() as session:
            await session.execute(
                sa.delete(KnowledgeVersion).where(KnowledgeVersion.id.in_(version_ids))
            )
            await session.execute(
                sa.update(KnowledgeDocument)
                .where(KnowledgeDocument.id.in_(document_ids))
                .values(current_version_id=None)
            )
            await session.execute(
                sa.delete(KnowledgeDocument).where(KnowledgeDocument.id.in_(document_ids))
            )
            await session.execute(sa.delete(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
            if _CREATED_SHOPS:
                await session.execute(sa.delete(Shop).where(Shop.id.in_(_CREATED_SHOPS)))
            await session.commit()
    finally:
        await engine.dispose()


async def test_image_endpoint_serves_the_original_file() -> None:
    _require_corpus_image()
    source_uri = CORPUS_IMAGE.relative_to(paths.KNOWLEDGE_DIR).as_posix()
    async with _client() as client:
        token, shop_id = await _login(client)
        document_id, _ = await _insert_image_document(
            shop_id=shop_id, source_uri=source_uri, mime_type="image/png", suffix=".png"
        )

        response = await client.get(
            f"/api/v1/knowledge-images/{document_id}", headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/png"
        assert response.content == CORPUS_IMAGE.read_bytes()


async def test_image_endpoint_hides_other_shops_and_non_images() -> None:
    _require_corpus_image()
    source_uri = CORPUS_IMAGE.relative_to(paths.KNOWLEDGE_DIR).as_posix()
    async with _client() as client:
        token, shop_id = await _login(client)
        # A document the caller may not read: created for a different shop.
        foreign_document, _ = await _insert_image_document(
            shop_id=await _insert_shop(),
            source_uri=source_uri,
            mime_type="image/png",
            suffix=".png",
        )
        # A document in the caller's shop, but it is a PDF, not an image.
        pdf_document, _ = await _insert_image_document(
            shop_id=shop_id,
            source_uri="policy/return-policy-cn-2026.10.1.md",
            mime_type="text/markdown",
            suffix=".md",
        )

        foreign = await client.get(
            f"/api/v1/knowledge-images/{foreign_document}", headers=_auth(token)
        )
        not_image = await client.get(
            f"/api/v1/knowledge-images/{pdf_document}", headers=_auth(token)
        )

        assert foreign.status_code == 404
        assert not_image.status_code == 404
        assert "image/png" in IMAGE_MIME_TYPES
