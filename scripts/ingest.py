"""Ingest knowledge documents into PostgreSQL and Milvus.

Usage::

    uv run python scripts/ingest.py                 # whole manifest
    uv run python scripts/ingest.py --only return-policy-cn
    uv run python scripts/ingest.py --manifest data/knowledge/manifest.json
    uv run python scripts/ingest.py --no-milvus     # metadata + chunks only

Failures are recorded on the knowledge version and ingestion job; the command exits with
status 1 if any document failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.rag.embeddings import build_embedding_provider
from shopmate_ecommerce_assistant.rag.errors import IngestionError
from shopmate_ecommerce_assistant.rag.ingest import IngestOutcome, ingest_source, load_manifest
from shopmate_ecommerce_assistant.rag.milvus_store import build_store


def _store_for(settings: Settings, *, enabled: bool):
    if not enabled:
        return None
    return build_store(settings)


async def _run(args: argparse.Namespace, manifest_path: Path) -> int:
    settings = get_settings()
    manifest = load_manifest(manifest_path)
    specs = manifest.filter(args.only)
    shop_id = stable_uuid("shop", manifest.shop_key)
    embedder = build_embedding_provider(settings)
    store = _store_for(settings, enabled=not args.no_milvus)

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    outcomes: list[IngestOutcome] = []
    try:
        async with factory() as session:
            for spec in specs:
                outcome = await ingest_source(
                    session=session,
                    settings=settings,
                    store=store,
                    embedder=embedder,
                    spec=spec,
                    base_dir=paths.KNOWLEDGE_DIR,
                    shop_id=shop_id,
                    milvus_enabled=not args.no_milvus,
                )
                outcomes.append(outcome)
                if args.json:
                    continue
                status = "ready" if outcome.ok else f"failed({outcome.error_code})"
                retry_hint = (
                    "  <-- 可重试：uv run python scripts/ingest.py --only "
                    f"{spec.document_key}@{spec.version}"
                    if outcome.retryable
                    else ""
                )
                print(
                    f"[{status}] {spec.document_key}@{spec.version} "
                    f"parents={outcome.parent_count} children={outcome.child_count} "
                    f"vectors={outcome.milvus_count}{retry_hint}"
                )
    finally:
        await engine.dispose()
        if store is not None:
            store.close()

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "document_id": str(outcome.document_id),
                        "version_id": str(outcome.version_id),
                        "job_id": str(outcome.job_id),
                        "status": outcome.status,
                        "parents": outcome.parent_count,
                        "children": outcome.child_count,
                        "vectors": outcome.milvus_count,
                        "error_code": outcome.error_code,
                        "error_message": outcome.error_message,
                    }
                    for outcome in outcomes
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        ready = sum(1 for outcome in outcomes if outcome.ok)
        failed = len(outcomes) - ready
        print(f"\n完成：{ready} 个版本 ready，{failed} 个失败，共 {len(outcomes)} 个版本。")
        for outcome in outcomes:
            if not outcome.ok:
                print(f"  失败原因：{outcome.error_code} - {outcome.error_message}")
    return 0 if all(outcome.ok for outcome in outcomes) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ShopMate 知识文档入库")
    parser.add_argument(
        "--manifest",
        default=str(paths.MANIFEST_PATH),
        help="清单文件路径，默认 data/knowledge/manifest.json",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="只入库指定 document_key 或文件名（可重复使用）",
    )
    parser.add_argument("--no-milvus", action="store_true", help="跳过 Milvus 写入，仅处理元数据")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        return asyncio.run(_run(args, manifest_path))
    except IngestionError as exc:
        print(f"ingest 失败：{exc.code} - {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ingest 失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
