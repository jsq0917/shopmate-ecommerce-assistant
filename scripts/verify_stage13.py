"""Independent recomputation of the stage-13 numbers quoted in ``docs/eval-report.md``.

Why a second implementation
---------------------------
The stage-13 acceptance was rejected partly because the report could not be reproduced
from the raw result on disk.  A summary function that feeds both the raw result and the
report proves nothing, so this script deliberately **does not import**
``scripts/eval_stage13.py``: it reads only ``data/eval/results/stage13-*.json`` and the
dataset files, recomputes every headline number from the per-case ``records``, and prints
a pass/fail table against what the raw result claims.

Usage::

    uv run python scripts/verify_stage13.py                       # newest raw result
    uv run python scripts/verify_stage13.py --raw <path>          # a specific run

Exit code is 1 when any recomputed value disagrees with the raw result, so it can gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "data" / "eval" / "results"
BUSINESS = ROOT / "data" / "eval" / "eval_questions.jsonl"
RETRIEVAL = ROOT / "data" / "eval" / "retrieval_cases.jsonl"

TOLERANCE = 0.0001
failures: list[str] = []


# ------------------------------------------------------------------ helpers
def percentile(values: list[float], quantile: float) -> float | None:
    """Linear interpolation between closest ranks (same definition as the report)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def count(rows: list[dict[str, Any]], predicate: str) -> int:
    """Count rows where ``predicate`` (a field name) is truthy."""
    return sum(1 for row in rows if row.get(predicate))


def compare(label: str, recomputed: Any, claimed: Any, *, tol: float = TOLERANCE) -> None:
    if isinstance(claimed, (int, float)) and isinstance(recomputed, (int, float)):
        ok = abs(float(recomputed) - float(claimed)) <= tol
    else:
        ok = recomputed == claimed
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label:<30} recomputed={recomputed!s:<12} claimed={claimed!s}")
    if not ok:
        failures.append(f"{label}: recomputed={recomputed} claimed={claimed}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


# ------------------------------------------------------------------ sections
def check_datasets(report: dict[str, Any]) -> None:
    print("== 数据集一致性 ==")
    for name, path in (("business", BUSINESS), ("retrieval", RETRIEVAL)):
        entry = report["datasets"][name]
        digest = sha256(path)
        cases = line_count(path)
        print(f"  {name}: disk sha256={digest[:16]}… cases={cases}")
        print(f"  {name}: 结果 sha256={entry['sha256'][:16]}… cases={entry['cases']}")
        compare(f"{name}.sha256", digest, entry["sha256"], tol=0)
        compare(f"{name}.cases", cases, entry["cases"], tol=0)


def check_retrieval(report: dict[str, Any]) -> None:
    print("\n== 检索（按 gold_rank 重算，不使用脚本的 recall_* 字段）==")
    for config, block in report["parts"]["retrieval"].items():
        if config == "optimisation" or "records" not in block:
            continue
        records = block["records"]
        summary = block["summary"]
        gold = [r for r in records if r.get("has_gold")]
        answerable = [r for r in records if r["expected_behavior"] == "answered"]
        print(f"  -- {config}: cases={len(records)} gold={len(gold)}")
        for k in (1, 3, 5, 10):
            hits = sum(1 for r in gold if (r.get("gold_rank") or 99) <= k)
            compare(f"{config}.recall@{k}", rate(hits, len(gold)), summary[f"recall_at_{k}"])
        reciprocal = [
            (1.0 / r["gold_rank"]) if (r.get("gold_rank") or 99) <= 10 else 0.0 for r in gold
        ]
        compare(f"{config}.mrr@10", mean(reciprocal), summary["mrr_at_10"])
        compare(
            f"{config}.behavior_accuracy",
            rate(count(records, "behavior_ok"), len(records)),
            summary["behavior_accuracy"],
        )
        compare(
            f"{config}.context_precision",
            mean([r["context_precision"] for r in records]),
            summary["context_precision"],
        )
        filled = [r["context_recall"] for r in records if r["context_recall"] is not None]
        compare(f"{config}.context_recall", mean(filled), summary["context_recall"])
        compare(
            f"{config}.citation_primary",
            rate(count(answerable, "citation_primary_ok"), len(answerable)),
            summary["citation_primary_rate"],
        )
        precise = [
            r["citation_precision"] for r in answerable if r["citation_precision"] is not None
        ]
        compare(f"{config}.citation_precision", mean(precise), summary["citation_precision"])
        compare(f"{config}.leak_cases", count(records, "leak"), summary["leak_cases"], tol=0)
        wrong_answer = sum(
            1
            for r in records
            if r["expected_behavior"] == "refused" and r["behavior"] == "answered"
        )
        compare(f"{config}.false_answer_cases", wrong_answer, summary["false_answer_cases"], tol=0)
        wrong_refusal = sum(1 for r in answerable if r["behavior"] != "answered")
        compare(
            f"{config}.false_refusal_cases", wrong_refusal, summary["false_refusal_cases"], tol=0
        )
        selected = [r["selected"] for r in records]
        compare(
            f"{config}.avg_selected",
            round(statistics.fmean(selected), 2),
            summary["avg_selected"],
        )
        latencies = [r["latency_ms"] for r in records if r["latency_ms"]]
        compare(f"{config}.p50_ms", percentile(latencies, 0.5), summary["latency"]["p50_ms"])


#: Same grid as ``scripts/eval_stage13.py::THRESHOLD_GRID`` — kept in sync by
#: ``tests/unit/test_verify_threshold_grid.py``.
THRESHOLD_GRID: tuple[float, ...] = (0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70)


def _recompute_sweep(records: list[dict[str, Any]]) -> dict[str, dict[str, int | float]]:
    """Recompute behaviour at every gate from the persisted records (no retrieval)."""
    sweep: dict[str, dict[str, int | float]] = {}
    for threshold in THRESHOLD_GRID:
        correct = false_answer = false_refusal = 0
        for row in records:
            if row["conflicts"]:
                behavior = "handoff"
            else:
                similarity = row["top_dense_similarity"]
                behavior = (
                    "answered"
                    if (similarity is not None and similarity >= threshold)
                    else "refused"
                )
            if behavior == row["expected_behavior"]:
                correct += 1
            if row["expected_behavior"] == "refused" and behavior == "answered":
                false_answer += 1
            if row["expected_behavior"] == "answered" and behavior != "answered":
                false_refusal += 1
        sweep[f"{threshold:.2f}"] = {
            "behavior_accuracy": rate(correct, len(records)),
            "false_answer_cases": false_answer,
            "false_refusal_cases": false_refusal,
        }
    return sweep


def _recompute_pick(sweep: dict[str, dict[str, int | float]]) -> float:
    """Same rule as ``eval_stage13._pick_threshold``: dev only, ties to the higher gate."""
    best_key: tuple[int, int, int, float] | None = None
    best_value = 0.62
    for raw_threshold, row in sweep.items():
        key = (
            round(float(row.get("behavior_accuracy") or 0.0) * 1000),
            -int(row.get("false_answer_cases") or 0),
            -int(row.get("false_refusal_cases") or 0),
            float(raw_threshold),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_value = float(raw_threshold)
    return best_value


def check_threshold_calibration(report: dict[str, Any]) -> None:
    """Recompute the dev-selected evidence gate and both split sweeps from records."""
    retrieval = report["parts"].get("retrieval") or {}
    baseline = retrieval.get("baseline_hybrid") or {}
    optimisation = retrieval.get("optimisation") or {}
    if "records" not in baseline:
        return
    records = baseline["records"]
    print("\n== 证据门槛标定（从 baseline_hybrid records 重算，不读脚本汇总）==")
    for split in ("dev", "test"):
        rows = [row for row in records if row["split"] == split]
        claimed = baseline.get(f"threshold_sweep_{split}")
        if claimed is None:
            print(f"  -- {split}: 原始结果未落盘 threshold_sweep_{split}")
            continue
        recomputed = _recompute_sweep(rows)
        print(f"  -- {split}: cases={len(rows)}")
        for threshold in THRESHOLD_GRID:
            label = f"{threshold:.2f}"
            row, want = recomputed[label], claimed[label]
            compare(
                f"{split}@{threshold}.accuracy",
                row["behavior_accuracy"],
                want["behavior_accuracy"],
            )
            compare(
                f"{split}@{threshold}.false_answer",
                row["false_answer_cases"],
                want["false_answer_cases"],
                tol=0,
            )
            compare(
                f"{split}@{threshold}.false_refusal",
                row["false_refusal_cases"],
                want["false_refusal_cases"],
                tol=0,
            )
    if optimisation:
        pick = _recompute_pick(_recompute_sweep([r for r in records if r["split"] == "dev"]))
        compare(
            "dev_calibrated_threshold",
            pick,
            optimisation.get("dev_calibrated_threshold"),
            tol=0,
        )


def check_business(report: dict[str, Any]) -> None:
    print("\n== 业务/安全（从 records 重算）==")
    block = report["parts"]["business"]
    records = block["records"]
    authorization = [r for r in records if "authorization" in r["tags"]]
    handoff_expected = [r for r in records if r["expected_behavior"] == "handoff"]
    refusal_expected = [
        r
        for r in records
        if r["expected_behavior"] == "refused" and "prompt_injection" not in r["tags"]
    ]
    injection = [r for r in records if "prompt_injection" in r["tags"]]
    print(f"  cases={len(records)} authorization={len(authorization)}")
    compare(
        "intent_accuracy",
        rate(count(records, "intent_ok"), len(records)),
        block["intent_accuracy"],
    )
    compare("tool_accuracy", rate(count(records, "tool_ok"), len(records)), block["tool_accuracy"])
    compare(
        "task_success_rate",
        rate(count(records, "task_success"), len(records)),
        block["task_success_rate"],
    )
    compare(
        "correct_refusal_rate",
        rate(
            sum(1 for r in refusal_expected if r["observed_behavior"] == "refused"),
            len(refusal_expected),
        ),
        block["correct_refusal_rate"],
    )
    compare(
        "no_fabrication_rate",
        rate(
            sum(1 for r in refusal_expected if r["observed_behavior"] in {"refused", "clarify"}),
            len(refusal_expected),
        ),
        block["no_fabrication_rate"],
    )
    compare("refusal_expected_cases", len(refusal_expected), block["refusal_expected_cases"], tol=0)
    compare("authorization_cases", len(authorization), block["authorization_cases"], tol=0)
    blocked = sum(1 for r in authorization if not r["leaks"])
    compare("unauthorized_blocked_cases", blocked, block["unauthorized_blocked_cases"], tol=0)
    compare(
        "unauthorized_blocked_rate",
        rate(blocked, len(authorization)),
        block["unauthorized_blocked_rate"],
    )
    compare(
        "handoff_recall",
        rate(count(handoff_expected, "handoff_required"), len(handoff_expected)),
        block["handoff_recall"],
    )
    escalated = [r for r in records if r["handoff_required"]]
    compare(
        "handoff_precision",
        rate(
            sum(1 for r in escalated if r["expected_behavior"] == "handoff"),
            len(escalated),
        ),
        block["handoff_precision"],
    )
    compare("leak_cases", count(records, "leaks"), block["leak_cases"], tol=0)
    compare(
        "injection_safety_rate",
        rate(count(injection, "safety_ok"), len(injection)),
        block["injection_safety_rate"],
    )
    errors = sum(1 for r in records if r["observed_behavior"] == "error")
    compare("error_turns", errors, block["error_turns"], tol=0)
    compare(
        "input_guard_blocks",
        count(records, "input_guard_blocked"),
        block["input_guard_blocks"],
        tol=0,
    )

    print("  -- 延迟拆分（latency_kind）")
    kinds: dict[str, int] = {}
    for record in records:
        kind = record.get("latency_kind") or "none"
        kinds[kind] = kinds.get(kind, 0) + 1
    print(f"     构成={kinds}")
    compare("latency_composition", kinds, block.get("latency_composition"), tol=0)
    chat = [r["latency_ms"] for r in records if r.get("latency_kind") == "chat_turn"]
    policy = [r["latency_ms"] for r in records if r.get("latency_kind") == "policy_retrieval"]
    first = [r["first_delta_ms"] for r in records if r.get("first_delta_ms") is not None]
    chat = [value for value in chat if value]
    policy = [value for value in policy if value]
    compare("chat_turn.n", len(chat), block["latency"]["n"], tol=0)
    compare("chat_turn.p50", percentile(chat, 0.5), block["latency"]["p50_ms"])
    compare("chat_turn.p95", percentile(chat, 0.95), block["latency"]["p95_ms"])
    retrieval_block = block["policy_retrieval_latency"]
    compare("policy_retrieval.n", len(policy), retrieval_block["n"], tol=0)
    compare("policy_retrieval.p50", percentile(policy, 0.5), retrieval_block["p50_ms"])
    compare("policy_retrieval.p95", percentile(policy, 0.95), retrieval_block["p95_ms"])
    compare("first_token.n", len(first), block["first_token"]["n"], tol=0)
    compare("first_token.p50", percentile(first, 0.5), block["first_token"]["p50_ms"])
    compare("first_token.p95", percentile(first, 0.95), block["first_token"]["p95_ms"])

    print("  -- 结构化生成代理")
    generation = block["generation"]
    rows = generation.get("records") or []
    structured = [row for row in rows if row.get("path") == "structured"]
    if structured:
        compare(
            "faithfulness_structured",
            mean([row["faithfulness_structured"] for row in structured]),
            generation.get("faithfulness_structured"),
        )
        compare(
            "answer_relevancy_cosine",
            mean([row["answer_relevancy_cosine"] for row in structured]),
            generation.get("answer_relevancy_cosine"),
        )
    else:
        # Deterministic function of (answer, tool payload) per turn; the payload is not
        # persisted, so this pair can only be recomputed by re-running the script.
        print(
            "     未落盘逐轮：faithfulness="
            f"{generation.get('faithfulness_structured')} "
            f"relevancy={generation.get('answer_relevancy_cosine')} "
            f"turns={generation.get('structured_turns')}（需重跑脚本，报告 2.11 已注明）"
        )


def check_policy(report: dict[str, Any]) -> None:
    block = report["parts"].get("policy_llm")
    if not block:
        print("\n== 政策答案：未运行 ==")
        return
    print(f"\n== 政策答案（模型：{block.get('answer_model') or '未配置'}）==")
    records = block["records"]
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    print(f"  cases={len(records)} status={counts}")
    compare("status_counts", counts, block["status_counts"], tol=0)
    answerable = [r for r in records if r.get("expected_behavior") == "answered"]
    no_answer = [r for r in records if r.get("expected_behavior") == "refused"]
    answered = [r for r in records if r["status"] == "answered"]
    compare("answered_rate", rate(len(answered), len(records)), block["answered_rate"])
    compare(
        "answer_rate_on_answerable",
        rate(len(answered), len(answerable)),
        block["answer_rate_on_answerable"],
    )
    compare(
        "refused_or_handoff_on_no_answer",
        rate(
            sum(1 for r in no_answer if r["status"] in {"refused", "handoff"}),
            len(no_answer),
        ),
        block["refused_or_handoff_on_no_answer"],
    )
    compare(
        "citation_compliance",
        rate(sum(1 for r in answered if r.get("citation_compliant")), len(answered)),
        block["citation_compliance"],
    )
    for key in ("faithfulness_llm", "relevancy_llm"):
        judged = [r[key] for r in records if r.get(key) is not None]
        compare(key, mean(judged), block[key])
    leaked = [r["case_id"] for r in records if r.get("sentinel_leaked")]
    compare("sentinel_leak_cases", leaked, block["sentinel_leak_cases"], tol=0)
    compare(
        "answer_prompt_tokens",
        sum(int(r["prompt_tokens"]) for r in records),
        block["tokens"]["answer_prompt"],
        tol=0,
    )
    compare(
        "answer_completion_tokens",
        sum(int(r["completion_tokens"]) for r in records),
        block["tokens"]["answer_completion"],
        tol=0,
    )
    latencies = [r["latency_ms"] for r in records]
    compare("policy.p50_ms", percentile(latencies, 0.5), block["latency"]["p50_ms"])
    compare("policy.p95_ms", percentile(latencies, 0.95), block["latency"]["p95_ms"])


def check_index(report: dict[str, Any]) -> None:
    print("\n== 索引规模（原始结果自带快照）==")
    index = report.get("index") or {}
    if index.get("status") == "unavailable":
        print(f"  快照不可用：{index.get('error')}")
        failures.append("index snapshot unavailable")
        return
    print(f"  postgres={index['postgres']}")
    print(f"  milvus={index['milvus']}")
    print(f"  note={index['note']}")


def check_report_text(raw_path: Path) -> None:
    """The report must quote the dataset sha256 that is actually on disk."""
    report_path = ROOT / "docs" / "eval-report.md"
    if not report_path.exists():
        return
    text = report_path.read_text(encoding="utf-8")
    digest = sha256(BUSINESS)
    print("\n== 报告文本 vs 磁盘数据集 ==")
    print(f"  磁盘 sha256={digest[:16]}… cases={line_count(BUSINESS)}")
    if digest[:16] in text:
        print("  报告已引用当前数据集 sha256 前缀")
    else:
        print("  报告未引用当前数据集 sha256 前缀")
        failures.append("报告 2.1 未引用当前数据集 sha256 前缀")
    print(f"  原始结果文件：{raw_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="独立复算阶段 13 指标")
    parser.add_argument("--raw", default="")
    args = parser.parse_args()

    if args.raw:
        raw_path = Path(args.raw)
    else:
        candidates = sorted(RESULTS_DIR.glob("stage13-*.json"), key=lambda p: p.stat().st_mtime)
        raw_path = candidates[-1]
    print(f"原始结果：{raw_path}")
    report = json.loads(raw_path.read_text(encoding="utf-8"))

    check_datasets(report)
    if "retrieval" in report["parts"]:
        check_retrieval(report)
        check_threshold_calibration(report)
    if "business" in report["parts"]:
        check_business(report)
    check_policy(report)
    check_index(report)
    check_report_text(raw_path)

    print("\n== 结论 ==")
    if failures:
        for item in failures:
            print(f"  - {item}")
        print(f"不一致项：{len(failures)}")
        return 1
    print("  全部一致（独立复算 == 原始结果）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
