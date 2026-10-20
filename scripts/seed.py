"""Seed ShopMate with deterministic synthetic commerce data and knowledge files.

Usage::

    uv run python scripts/seed.py
    uv run python scripts/seed.py --json

The command is idempotent: every row uses a natural-key derived UUID and is upserted, so
running it repeatedly keeps table counts stable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.synthetic.seed import run_seed


def _print_human(report) -> None:
    print("ShopMate 合成数据种子完成（is_synthetic=true）")
    for table, count in report.counts.items():
        print(f"  {table:<20} {count:>5}")
    print(f"  knowledge 文档版本     {report.manifest_documents:>5}")
    print(f"  FAQ 条目              {report.faq_entries:>5}")
    print(f"  评测问题              {report.eval_cases:>5}")
    print(f"  数据集指纹            {report.fingerprint}")
    print("生成文件：")
    for path in report.files[:8]:
        print(f"  {path}")
    if len(report.files) > 8:
        print(f"  ... 其余 {len(report.files) - 8} 个文件")


async def _run(as_json: bool) -> int:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            report = await run_seed(session)
    finally:
        await engine.dispose()

    if as_json:
        print(
            json.dumps(
                {
                    "counts": report.counts,
                    "files": report.files,
                    "fingerprint": report.fingerprint,
                    "manifest_documents": report.manifest_documents,
                    "faq_entries": report.faq_entries,
                    "eval_cases": report.eval_cases,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_human(report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 ShopMate 合成数据与知识源文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.json))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"seed 失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
