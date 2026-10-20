"""Smoke test for the local BGE-M3 provider (no database, no Milvus).

Usage::

    uv run python scripts/smoke_embedding.py
"""

from __future__ import annotations

import math

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.rag.embeddings import build_embedding_provider


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def main() -> int:
    settings = get_settings()
    provider = build_embedding_provider(settings)
    metadata = provider.warmup()
    print(f"model={metadata.model} dim={metadata.dimension} revision={metadata.revision}")
    print(f"fingerprint={metadata.fingerprint}")

    texts = [
        "七天无理由退货政策：消费者自签收之日起七日内可以申请无理由退货。",
        "发票抬头需填写完整企业名称与纳税人识别号，支持电子发票。",
        "偏远地区订单按重量收取附加费，首重 1 公斤 12 元。",
    ]
    vectors = provider.embed_documents_hybrid(texts)
    for index, vector in enumerate(vectors):
        norm = math.sqrt(math.fsum(value * value for value in vector.dense))
        print(
            f"[doc {index}] dim={len(vector.dense)} norm={norm:.6f} "
            f"sparse_terms={len(vector.sparse)}"
        )

    queries = {
        "退货怎么算时间": 0,
        "发票抬头怎么写": 1,
        "偏远地区运费怎么算": 2,
        "门店停车场在哪里": None,
    }
    for query, expected in queries.items():
        vector = provider.embed_query_hybrid(query)
        scores = [_cosine(vector.dense, doc.dense) for doc in vectors]
        best = max(range(len(scores)), key=lambda index: scores[index])
        flag = "ok" if expected == best else ("n/a" if expected is None else "MISMATCH")
        print(
            f"query={query!r} best=doc{best} scores="
            + ", ".join(f"{score:.4f}" for score in scores)
            + f" sparse_terms={len(vector.sparse)} -> {flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
