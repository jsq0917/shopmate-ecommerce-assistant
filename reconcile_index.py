"""Final index reconciliation: PG (enabled/total chunks, ready versions) vs
Milvus rows, plus id-level intersection / orphan / missing counts."""

from __future__ import annotations

import asyncio

import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.rag.milvus_store import build_store


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    store = build_store(settings)
    async with factory() as session:
        enabled = (
            await session.execute(
                sa.text(
                    "select count(*) from knowledge_chunks "
                    "where deleted_at is null and is_enabled = true"
                )
            )
        ).scalar_one()
        total = (
            await session.execute(
                sa.text("select count(*) from knowledge_chunks where deleted_at is null")
            )
        ).scalar_one()
        ready = (
            await session.execute(
                sa.text("select count(*) from knowledge_versions where parse_status='ready'")
            )
        ).scalar_one()
        docs = (
            await session.execute(sa.text("select count(*) from knowledge_documents"))
        ).scalar_one()
        stale_titles = (
            (
                await session.execute(
                    sa.text(
                        "select title from knowledge_documents where title like '%店铺退货政策%'"
                    )
                )
            )
            .scalars()
            .all()
        )
        pg_ids = set(
            (
                await session.scalars(
                    sa.text("select id::text from knowledge_chunks where deleted_at is null")
                )
            ).all()
        )
    rows = store.client.query(store.collection, filter="", output_fields=["chunk_id"], limit=1000)
    milvus_ids = {str(r["chunk_id"]) for r in rows}
    await engine.dispose()
    store.close()

    print(f"PG documents            : {docs}")
    print(f"PG ready versions       : {ready}")
    print(f"PG chunks enabled       : {enabled}")
    print(f"PG chunks total         : {total} (disabled historical: {total - enabled})")
    print(f"Milvus rows             : {len(milvus_ids)}")
    print(f"intersection            : {len(pg_ids & milvus_ids)}")
    print(f"orphans (milvus not pg) : {len(milvus_ids - pg_ids)}")
    print(f"missing (pg not milvus) : {len(pg_ids - milvus_ids)}")
    print(f"stale shop-fee docs     : {stale_titles}")


asyncio.run(main())
