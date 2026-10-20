"""Retrieval evaluation: hybrid (dense+sparse RRF) versus dense-only ablation.

Dataset: ``data/eval/retrieval_cases.jsonl`` — five categories (normal, no_answer,
expired, conflict, cross_shop). Every run stores raw per-case results plus a summary so a
number can always be traced back to a command, a dataset hash and a model fingerprint.

The dense-only run exists **only** to prove the sparse branch contributes; it is labelled
``dense_only_ablation`` and must never be used to answer users.

Usage::

    uv run python scripts/eval_retrieval.py
    uv run python scripts/eval_retrieval.py --modes hybrid
    uv run python scripts/eval_retrieval.py --skip-conflict-fixtures
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.rag.embeddings import build_embedding_provider
from shopmate_ecommerce_assistant.rag.errors import RetrievalError
from shopmate_ecommerce_assistant.rag.ingest import SourceSpec, ingest_source
from shopmate_ecommerce_assistant.rag.milvus_store import build_store
from shopmate_ecommerce_assistant.rag.retrieval import (
    DocumentRetriever,
    RetrievalMode,
    RetrievalScope,
    session_authorizer,
)

RESULTS_DIR = paths.EVAL_DIR / "results"
CONFLICT_KB = "eval-conflict"
CONFLICT_KEY = "conflict-return-fee"
CONFLICT_TITLE = "退货手续费说明（评测冲突样本）"


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One evaluation question with its expected behaviour."""

    case_id: str
    category: str
    question: str
    at: datetime
    region: str | None
    locale: str | None
    shop: str
    knowledge_base: str | None
    expected_titles: tuple[str, ...]
    expected_version: str | None
    expected_phrases: tuple[str, ...]
    forbidden_titles: tuple[str, ...]
    forbidden_versions: tuple[str, ...]
    should_answer: bool
    expect_conflict: bool

    @property
    def expected_behavior(self) -> str:
        if self.expect_conflict:
            return "handoff"
        return "answered" if self.should_answer else "refused"


def _parse_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cases.append(
            EvalCase(
                case_id=raw["case_id"],
                category=raw["category"],
                question=raw["question"],
                at=datetime.fromisoformat(raw["at"].replace("Z", "+00:00")),
                region=raw.get("region"),
                locale=raw.get("locale"),
                shop=raw.get("shop", "demo"),
                knowledge_base=raw.get("knowledge_base"),
                expected_titles=tuple(raw.get("expected_titles", [])),
                expected_version=raw.get("expected_version"),
                expected_phrases=tuple(raw.get("expected_phrases", [])),
                forbidden_titles=tuple(raw.get("forbidden_titles", [])),
                forbidden_versions=tuple(raw.get("forbidden_versions", [])),
                should_answer=bool(raw.get("should_answer", True)),
                expect_conflict=bool(raw.get("expect_conflict", False)),
            )
        )
    return cases


def _conflict_specs() -> list[SourceSpec]:
    """Two overlapping versions of one document: a deliberate governance conflict."""
    return [
        SourceSpec(
            document_key=CONFLICT_KEY,
            title=CONFLICT_TITLE,
            doc_type="policy",
            version="2026.09.1",
            effective_from=datetime(2026, 9, 1, tzinfo=UTC),
            effective_to=datetime(2027, 6, 1, tzinfo=UTC),
            locale="zh-CN",
            region="CN",
            knowledge_base=CONFLICT_KB,
            file="conflict/conflict-return-fee-2026.09.1.md",
        ),
        SourceSpec(
            document_key=CONFLICT_KEY,
            title=CONFLICT_TITLE,
            doc_type="policy",
            version="2026.10.1",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=datetime(2027, 6, 1, tzinfo=UTC),
            locale="zh-CN",
            region="CN",
            knowledge_base=CONFLICT_KB,
            file="conflict/conflict-return-fee-2026.10.1.md",
        ),
    ]


async def _ingest_conflict_fixtures(session: Any, provider: Any, store: Any, shop_id: UUID) -> int:
    ingested = 0
    for spec in _conflict_specs():
        outcome = await ingest_source(
            session=session,
            settings=get_settings(),
            store=store,
            embedder=provider,
            spec=spec,
            base_dir=paths.EVAL_DIR,
            shop_id=shop_id,
        )
        if not outcome.ok:
            raise RuntimeError(f"冲突样本入库失败：{outcome.error_code} {outcome.error_message}")
        ingested += outcome.child_count
    return ingested


async def _cleanup_conflict_fixtures(session: Any, store: Any, shop_id: UUID) -> None:
    kb_id = stable_uuid("knowledge_base", str(shop_id), CONFLICT_KB)
    version_ids = (
        await session.scalars(
            sa.select(KnowledgeVersion.id).where(
                KnowledgeVersion.shop_id == shop_id,
                KnowledgeVersion.document_id.in_(
                    sa.select(KnowledgeDocument.id).where(
                        KnowledgeDocument.knowledge_base_id == kb_id,
                        KnowledgeDocument.shop_id == shop_id,
                    )
                ),
            )
        )
    ).all()
    for version_id in version_ids:
        try:
            store.delete_version(str(version_id))
        except Exception:  # pragma: no cover - cleanup is best effort
            pass
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
    document_ids = (
        await session.scalars(
            sa.select(KnowledgeDocument.id).where(
                KnowledgeDocument.knowledge_base_id == kb_id,
                KnowledgeDocument.shop_id == shop_id,
            )
        )
    ).all()
    for document_id in document_ids:
        await session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(current_version_id=None)
        )
        await session.execute(
            sa.delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
    await session.execute(sa.delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await session.commit()


def _scope(case: EvalCase, shop_id: UUID) -> RetrievalScope:
    if case.shop == "demo":
        resolved_shop = str(shop_id)
    else:
        resolved_shop = case.shop
    kb_id = (
        str(stable_uuid("knowledge_base", resolved_shop, case.knowledge_base))
        if case.knowledge_base
        else None
    )
    return RetrievalScope(
        shop_id=resolved_shop,
        knowledge_base_id=kb_id,
        locale=case.locale,
        region=case.region,
        at=case.at,
    )


def _evaluate_case(case: EvalCase, result: Any) -> dict[str, Any]:
    citations = list(result.citations)
    titles = [citation.title for citation in citations]
    first_hit = next(
        (index for index, title in enumerate(titles) if title in case.expected_titles), None
    )
    retrieved_text = "\n".join(item.text for item in result.evidence)
    phrase_hits = sum(1 for phrase in case.expected_phrases if phrase in retrieved_text)
    phrase_recall = (phrase_hits / len(case.expected_phrases)) if case.expected_phrases else 1.0
    forbidden = [title for title in titles if title in case.forbidden_titles]
    version_leaks = [
        citation.version
        for citation in citations
        if citation.title in case.expected_titles and citation.version in case.forbidden_versions
    ]
    if case.expect_conflict:
        if result.conflicts:
            behavior = "handoff"
        else:
            behavior = "answered" if result.evidence_sufficient else "refused"
    else:
        behavior = "answered" if result.evidence_sufficient else "refused"
    return {
        "case_id": case.case_id,
        "category": case.category,
        "behavior": behavior,
        "expected_behavior": case.expected_behavior,
        "behavior_ok": behavior == case.expected_behavior,
        "retrieval_hit": first_hit is not None,
        "gold_rank": (first_hit + 1) if first_hit is not None else None,
        "gold_in_top1": first_hit == 0,
        "gold_in_top3": first_hit is not None and first_hit < 3,
        "mrr": (1.0 / (first_hit + 1)) if first_hit is not None else 0.0,
        "phrase_recall": phrase_recall,
        "forbidden_titles": forbidden,
        "version_leaks": version_leaks,
        "leak": bool(forbidden or version_leaks),
        "conflict_detected": bool(result.conflicts),
        "selected": len(result.evidence),
        "top_dense_similarity": (
            None if result.top_dense_similarity is None else round(result.top_dense_similarity, 4)
        ),
        "citations": [
            {
                "citation_id": citation.citation_id,
                "label": citation.label,
                "title": citation.title,
                "version": citation.version,
                "page_no": citation.page_no,
                "chunk_id": citation.chunk_id,
                "snippet": citation.snippet[:120],
                "dense_similarity": citation.dense_similarity,
            }
            for citation in citations
        ],
        "audit": {
            "fused_candidates": result.audit.get("fused_candidates"),
            "authorized_candidates": result.audit.get("authorized_candidates"),
            "rejected": result.audit.get("rejected"),
            "rrf_k": result.audit.get("rrf_k"),
            "dense_limit": result.audit.get("dense_limit"),
            "sparse_limit": result.audit.get("sparse_limit"),
            "branch": result.audit.get("branch"),
            "latency_ms": result.audit.get("latency_ms"),
        },
    }


def _summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    answerable = [record for record in records if record["expected_behavior"] == "answered"]
    gold_ranks = [record["gold_rank"] for record in records if record.get("gold_rank") is not None]
    return {
        "top1_rate": round(
            sum(1 for record in records if record.get("gold_in_top1")) / len(records), 4
        ),
        "top3_rate": round(
            sum(1 for record in records if record.get("gold_in_top3")) / len(records), 4
        ),
        "mean_gold_rank": (round(statistics.fmean(gold_ranks), 2) if gold_ranks else None),
        "cases": len(records),
        "behavior_accuracy": round(
            sum(1 for record in records if record["behavior_ok"]) / len(records), 4
        ),
        "retrieval_hit_rate": round(
            sum(1 for record in records if record["retrieval_hit"]) / len(records), 4
        ),
        "mrr": round(statistics.fmean(record["mrr"] for record in records), 4),
        "phrase_recall": round(statistics.fmean(record["phrase_recall"] for record in records), 4),
        "leak_cases": sum(1 for record in records if record["leak"]),
        "false_answer_cases": sum(
            1
            for record in records
            if record["expected_behavior"] == "refused" and record["behavior"] == "answered"
        ),
        "false_refusal_cases": sum(1 for record in answerable if record["behavior"] != "answered"),
        "avg_selected": round(statistics.fmean(record["selected"] for record in records), 2),
        "avg_latency_ms": round(
            statistics.fmean(record["audit"]["latency_ms"] or 0.0 for record in records),
            2,
        ),
    }


def _compare_modes(runs: dict[str, Any]) -> dict[str, Any]:
    """Compare fused orderings between modes to show whether the sparse branch acts.

    Identical metrics do not prove a branch is dead: on an easy corpus both modes can
    return the right document first. This comparison reports how often the returned
    ranking actually differs, which is the observable effect of fusing a second branch.
    """
    hybrid = runs.get(RetrievalMode.HYBRID.value)
    dense = runs.get(RetrievalMode.DENSE_ONLY_ABLATION.value)
    if not hybrid or not dense:
        return {}
    dense_by_id = {record["case_id"]: record for record in dense["records"]}
    differences: list[dict[str, Any]] = []
    compared = 0
    for record in hybrid["records"]:
        other = dense_by_id.get(record["case_id"])
        if other is None:
            continue
        compared += 1
        hybrid_ids = [citation["chunk_id"] for citation in record["citations"]]
        dense_ids = [citation["chunk_id"] for citation in other["citations"]]
        changed = sum(
            1 for left, right in zip(hybrid_ids, dense_ids, strict=False) if left != right
        )
        if changed or len(hybrid_ids) != len(dense_ids):
            differences.append(
                {
                    "case_id": record["case_id"],
                    "category": record["category"],
                    "positions_changed": changed,
                    "hybrid_count": len(hybrid_ids),
                    "dense_count": len(dense_ids),
                }
            )
    return {
        "cases_compared": compared,
        "cases_with_ranking_difference": len(differences),
        "details": differences,
    }


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    provider = build_embedding_provider(settings)
    metadata = provider.warmup()
    store = build_store(settings)
    store.ensure_collection()
    cases = _parse_cases(Path(args.dataset).expanduser().resolve())  # noqa: ASYNC240
    shop_id = stable_uuid("shop", "demo")
    started = datetime.now(UTC)

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    modes = [RetrievalMode(mode) for mode in args.modes]
    report: dict[str, Any] = {
        "generated_at": started.isoformat(),
        "dataset": str(Path(args.dataset).name),
        "dataset_sha256": hashlib.sha256(
            Path(args.dataset).read_bytes()  # noqa: ASYNC240 - local fixture read
        ).hexdigest(),
        "cases": len(cases),
        "embedding": metadata.as_dict(),
        "config": {
            "dense_limit": settings.retrieval_dense_limit,
            "sparse_limit": settings.retrieval_sparse_limit,
            "rrf_k": settings.retrieval_rrf_k,
            "candidate_limit": settings.retrieval_candidate_limit,
            "min_chunks": settings.retrieval_min_chunks,
            "max_chunks": settings.retrieval_max_chunks,
            "min_evidence_similarity": settings.policy_min_evidence_similarity,
            "reranker_enabled": settings.reranker_enabled,
        },
        "runs": {},
    }
    try:
        async with factory() as session:
            if not args.skip_conflict_fixtures:
                chunks = await _ingest_conflict_fixtures(session, provider, store, shop_id)
                print(f"冲突样本已入库：{chunks} 个子块", flush=True)
            for mode in modes:
                retriever = DocumentRetriever(
                    settings=settings,
                    provider=provider,
                    store=store,
                    authorizer=session_authorizer(session),
                )
                records: list[dict[str, Any]] = []
                for case in cases:
                    try:
                        result = await retriever.retrieve(
                            case.question, _scope(case, shop_id), mode=mode
                        )
                    except RetrievalError as exc:
                        records.append(
                            {
                                "case_id": case.case_id,
                                "category": case.category,
                                "behavior": "error",
                                "expected_behavior": case.expected_behavior,
                                "behavior_ok": False,
                                "retrieval_hit": False,
                                "mrr": 0.0,
                                "phrase_recall": 0.0,
                                "forbidden_titles": [],
                                "version_leaks": [],
                                "leak": False,
                                "conflict_detected": False,
                                "selected": 0,
                                "top_dense_similarity": None,
                                "citations": [],
                                "audit": {
                                    "error": {"code": exc.code, "message": exc.message},
                                    "latency_ms": None,
                                    "fused_candidates": 0,
                                    "rrf_k": None,
                                    "dense_limit": None,
                                    "sparse_limit": None,
                                    "branch": None,
                                    "rejected": None,
                                },
                            }
                        )
                        continue
                    record = _evaluate_case(case, result)
                    record["question"] = case.question
                    records.append(record)
                    status = "hit" if record["retrieval_hit"] else "miss"
                    print(
                        f"[{mode.value}/{case.category}] {case.case_id} {status} "
                        f"behavior={record['behavior']} selected={record['selected']}",
                        flush=True,
                    )
                by_category: dict[str, dict[str, Any]] = {}
                for category in sorted({record["category"] for record in records}):
                    by_category[category] = _summarise(
                        [record for record in records if record["category"] == category]
                    )
                report["runs"][mode.value] = {
                    "summary": _summarise(records),
                    "by_category": by_category,
                    "records": records,
                }
            report["mode_comparison"] = _compare_modes(report["runs"])
            if not args.skip_conflict_fixtures:
                await _cleanup_conflict_fixtures(session, store, shop_id)
    finally:
        await engine.dispose()
        store.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    raw_path = Path(args.output) if args.output else RESULTS_DIR / f"retrieval-{stamp}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = raw_path.with_suffix(".md")
    lines = [
        "# 阶段 7 检索评测结果",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 数据集：`{report['dataset']}`"
        f"（sha256 `{report['dataset_sha256'][:16]}`，{report['cases']} 条）",
        f"- 模型：`{metadata.model}`｜维度 {metadata.dimension}｜revision `{metadata.revision}`"
        f"｜权重指纹 `{metadata.fingerprint}`",
        f"- 检索配置：dense top{settings.retrieval_dense_limit} + sparse top"
        f"{settings.retrieval_sparse_limit}，RRF k={settings.retrieval_rrf_k}，"
        f"最终 {settings.retrieval_min_chunks}-{settings.retrieval_max_chunks} 个片段，"
        f"证据阈值 {settings.policy_min_evidence_similarity}",
        "",
        "| 模式 | 用例 | 行为正确率 | 命中率 | MRR | 片段召回 | 泄漏用例 "
        "| 误答 | 误拒 | 平均片段 | 平均耗时(ms) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, run in report["runs"].items():
        summary = run["summary"]
        lines.append(
            f"| {mode} | {summary['cases']} | {summary['behavior_accuracy']} | "
            f"{summary['retrieval_hit_rate']} | {summary['mrr']} | {summary['phrase_recall']} | "
            f"{summary['leak_cases']} | {summary['false_answer_cases']} | "
            f"{summary['false_refusal_cases']} | {summary['avg_selected']} | "
            f"{summary['avg_latency_ms']} |"
        )
    comparison = report.get("mode_comparison") or {}
    if comparison:
        lines += [
            "",
            "## 双路 vs dense-only：排序差异",
            "",
            f"- 对比用例：{comparison['cases_compared']}",
            f"- 排序发生变化的用例：{comparison['cases_with_ranking_difference']}",
            "",
            "排序差异说明稀疏支路确实参与了融合；指标相同则说明该数据集上 dense 已足够，"
            "不能据此宣称双路提升了召回。",
            "",
        ]
        if comparison["details"]:
            lines.append("| 用例 | 类别 | 变动位置数 | hybrid 片段数 | dense 片段数 |")
            lines.append("|---|---|---|---|---|")
            for detail in comparison["details"]:
                lines.append(
                    f"| {detail['case_id']} | {detail['category']} | "
                    f"{detail['positions_changed']} | {detail['hybrid_count']} | "
                    f"{detail['dense_count']} |"
                )
            lines.append("")
    lines += ["", "## 分类结果", ""]
    for mode, run in report["runs"].items():
        lines.append(f"### {mode}")
        lines.append("")
        lines.append("| 类别 | 用例 | 行为正确率 | 命中率 | MRR | 误答 | 误拒 |")
        lines.append("|---|---|---|---|---|---|---|")
        for category, summary in run["by_category"].items():
            lines.append(
                f"| {category} | {summary['cases']} | {summary['behavior_accuracy']} | "
                f"{summary['retrieval_hit_rate']} | {summary['mrr']} | "
                f"{summary['false_answer_cases']} | {summary['false_refusal_cases']} |"
            )
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("")
    for mode, run in report["runs"].items():
        summary = run["summary"]
        print(
            f"{mode}: accuracy={summary['behavior_accuracy']} hit={summary['retrieval_hit_rate']} "
            f"mrr={summary['mrr']} phrase={summary['phrase_recall']} leak={summary['leak_cases']} "
            f"false_answer={summary['false_answer_cases']} "
            f"false_refusal={summary['false_refusal_cases']}"
        )
    print(f"原始结果：{raw_path}")
    print(f"摘要：{md_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ShopMate 政策检索评测")
    parser.add_argument("--dataset", default=str(paths.EVAL_DIR / "retrieval_cases.jsonl"))
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["hybrid", "dense_only_ablation"],
        choices=["hybrid", "dense_only_ablation"],
    )
    parser.add_argument("--output", default="", help="原始结果 JSON 路径")
    parser.add_argument(
        "--skip-conflict-fixtures",
        action="store_true",
        help="跳过冲突样本入库与清理（需要索引中已存在 eval-conflict 知识库）",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"评测失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
