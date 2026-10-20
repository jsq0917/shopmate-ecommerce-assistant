"""Rebuild the knowledge collection for BGE-M3 and re-import every manifest document.

Stage 5 wrote 384-dimensional hashing vectors into a dense-only collection. BGE-M3 produces
1024-dimensional dense vectors *plus* sparse lexical weights, so the old collection cannot
be migrated in place: it is dropped, recreated with both indexes, and every document version
is re-embedded and re-imported.

Usage::

    uv run python scripts/rebuild_knowledge_index.py --yes
    uv run python scripts/rebuild_knowledge_index.py --yes --only return-policy-cn
    uv run python scripts/rebuild_knowledge_index.py --verify-only

The command fails (exit 1) when verification does not hold: row counts must match
PostgreSQL children, sparse coverage must be 100%, dense must be 1024-dimensional and every
vector must be L2-normalised.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import KnowledgeChunk, KnowledgeVersion
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.rag.embeddings import (
    DENSE_DIMENSION,
    build_embedding_provider,
)
from shopmate_ecommerce_assistant.rag.errors import IngestionError
from shopmate_ecommerce_assistant.rag.ingest import IngestOutcome, ingest_source, load_manifest
from shopmate_ecommerce_assistant.rag.ingest.manifest import SourceSpec
from shopmate_ecommerce_assistant.rag.milvus_store import (
    MilvusKnowledgeStore,
    build_store,
    collect_vector_stats,
)


def _version_id(shop_id: Any, spec: SourceSpec) -> Any:
    document_id = stable_uuid("document", str(shop_id), spec.knowledge_base, spec.document_key)
    return stable_uuid("version", str(document_id), spec.version)


async def _postgres_counts(version_ids: list[Any]) -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            children = await session.scalar(
                sa.select(sa.func.count())
                .select_from(KnowledgeChunk)
                .where(
                    KnowledgeChunk.version_id.in_(version_ids),
                    KnowledgeChunk.is_enabled.is_(True),
                    KnowledgeChunk.deleted_at.is_(None),
                )
            )
            with_embedding = await session.scalar(
                sa.select(sa.func.count())
                .select_from(KnowledgeChunk)
                .where(
                    KnowledgeChunk.version_id.in_(version_ids),
                    KnowledgeChunk.is_enabled.is_(True),
                    KnowledgeChunk.metadata_jsonb["embedding"]["fingerprint"].astext.isnot(None),
                )
            )
            ready_versions = await session.scalar(
                sa.select(sa.func.count())
                .select_from(KnowledgeVersion)
                .where(
                    KnowledgeVersion.id.in_(version_ids),
                    KnowledgeVersion.parse_status == "ready",
                )
            )
    finally:
        await engine.dispose()
    return {
        "children": int(children or 0),
        "children_with_embedding_metadata": int(with_embedding or 0),
        "ready_versions": int(ready_versions or 0),
    }


def _verify(
    store: MilvusKnowledgeStore,
    settings: Settings,
    pg: dict[str, int],
    expected_fingerprint: str | None,
) -> tuple[dict[str, Any], list[str]]:
    stats = collect_vector_stats(store)
    problems: list[str] = []
    if stats["rows"] != pg["children"]:
        problems.append(f"Milvus 行数 {stats['rows']} 与 PG 子块数 {pg['children']} 不一致")
    if stats["sparse_coverage"] < 1.0:
        problems.append(f"sparse 非空率 {stats['sparse_coverage']:.4f} 不是 100%")
    if stats["dense_dimensions"] != [DENSE_DIMENSION]:
        problems.append(f"dense 维度为 {stats['dense_dimensions']}，期望 [{DENSE_DIMENSION}]")
    if stats["norms_outside_tolerance"]:
        problems.append(f"{stats['norms_outside_tolerance']} 个向量范数偏离 1.0")
    models = set(stats["embedding_models"])
    if models - {"bge-m3"}:
        problems.append(f"存在非 bge-m3 的 embedding_model：{sorted(models - {'bge-m3'})}")
    if pg["children_with_embedding_metadata"] != pg["children"]:
        problems.append(
            "部分子块缺少 metadata_jsonb.embedding 指纹："
            f"{pg['children_with_embedding_metadata']}/{pg['children']}"
        )
    report = {
        "collection": settings.milvus_collection,
        "expected_dimension": DENSE_DIMENSION,
        "postgres": pg,
        "milvus": stats,
        "expected_fingerprint": expected_fingerprint,
        "runtime_fingerprint": stats["embedding_models"],
        "checked_at": datetime.now(UTC).isoformat(),
        "problems": problems,
    }
    return report, problems


async def _rebuild(args: argparse.Namespace, manifest_path: Path) -> int:
    settings = get_settings()
    manifest = load_manifest(manifest_path)
    specs = manifest.filter(args.only)
    shop_id = stable_uuid("shop", manifest.shop_key)
    version_ids = [_version_id(shop_id, spec) for spec in specs]

    provider = build_embedding_provider(settings)
    metadata = provider.warmup()
    print(
        f"模型：{metadata.model}｜维度 {metadata.dimension}｜revision {metadata.revision}"
        f"｜权重指纹 {metadata.fingerprint}",
        flush=True,
    )

    store = build_store(settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    outcomes: list[IngestOutcome] = []
    try:
        if store.client.has_collection(store.collection) and not args.verify_only:
            try:
                old = store.describe()
                print(f"现有 collection：{old}", flush=True)
            except IngestionError:
                old = {}
            if not args.yes:
                print(
                    "将删除并重建 collection。该操作会清空向量库中的知识向量"
                    "（PostgreSQL 元数据保留，可重新导入）。确认请加 --yes。",
                    file=sys.stderr,
                )
                return 2
            store.drop_collection()
        store.ensure_collection()

        if not args.verify_only:
            async with factory() as session:
                for spec in specs:
                    outcome = await ingest_source(
                        session=session,
                        settings=settings,
                        store=store,
                        embedder=provider,
                        spec=spec,
                        base_dir=paths.KNOWLEDGE_DIR,
                        shop_id=shop_id,
                    )
                    outcomes.append(outcome)
                    status = "ready" if outcome.ok else f"failed({outcome.error_code})"
                    print(
                        f"[{status}] {spec.document_key}@{spec.version} "
                        f"children={outcome.child_count} vectors={outcome.milvus_count}"
                        + (
                            "  <-- 可重试：uv run python scripts/ingest.py --only "
                            f"{spec.document_key}"
                            if outcome.retryable
                            else ""
                        ),
                        flush=True,
                    )

        pg = await _postgres_counts(version_ids)
        store.flush()
        report, problems = _verify(store, settings, pg, metadata.fingerprint)
        for key in ("rows", "sparse_coverage", "dense_dimensions", "embedding_models"):
            print(f"  {key}: {report['milvus'][key]}", flush=True)
        print(f"  postgres: {pg}", flush=True)

        if args.report:
            target = Path(args.report).expanduser().resolve()  # noqa: ASYNC240
            target.parent.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
            target.write_text(  # noqa: ASYNC240 - local report write
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"报告已写入：{target}", flush=True)

        if problems:
            print("校验失败：", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1

        failed = [outcome for outcome in outcomes if not outcome.ok]
        print(
            f"重建完成：{len(outcomes)} 个版本，失败 {len(failed)} 个；校验全部通过。",
            flush=True,
        )
        return 0 if not failed else 1
    finally:
        await engine.dispose()
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="重建 ShopMate 知识向量集合（BGE-M3 双向量）")
    parser.add_argument("--manifest", default=str(paths.MANIFEST_PATH))
    parser.add_argument("--only", action="append", default=None, help="只处理指定 document_key")
    parser.add_argument("--yes", action="store_true", help="确认删除并重建 collection")
    parser.add_argument("--verify-only", action="store_true", help="只做校验，不重建")
    parser.add_argument("--report", default="", help="把校验报告写入指定 JSON 路径")
    args = parser.parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        return asyncio.run(_rebuild(args, manifest_path))
    except IngestionError as exc:
        print(f"重建失败：{exc.code} - {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"重建失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
