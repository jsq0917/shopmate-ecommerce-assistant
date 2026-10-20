"""Knowledge source manifest.

The manifest is the declarative input for ``scripts/ingest.py``. It pins every metadata
field the retrieval contract filters on: shop, knowledge base, document type, locale,
region, version and validity window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shopmate_ecommerce_assistant.rag.errors import IngestionError

MANIFEST_VERSION = 1


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """One document version to ingest."""

    document_key: str
    title: str
    doc_type: str
    version: str
    effective_from: datetime
    effective_to: datetime | None
    locale: str
    region: str
    knowledge_base: str
    file: str

    def resolve(self, base_dir: Path) -> Path:
        """Resolve the file inside the controlled knowledge directory.

        Raises:
            IngestionError: the path escapes ``base_dir``.
        """
        candidate = (base_dir / self.file).resolve()
        root = base_dir.resolve()
        if not candidate.is_relative_to(root):
            raise IngestionError("UNSAFE_SOURCE_PATH", "文档路径超出受控目录")
        return candidate


@dataclass(frozen=True, slots=True)
class Manifest:
    """Parsed manifest with its shop key."""

    shop_key: str
    documents: tuple[SourceSpec, ...]

    def filter(self, keys: list[str] | None) -> list[SourceSpec]:
        """Return the specs matching ``keys`` (document_key or file stem)."""
        if not keys:
            return list(self.documents)
        wanted = set(keys)
        selected = [
            spec
            for spec in self.documents
            if spec.document_key in wanted
            or Path(spec.file).stem in wanted
            or f"{spec.document_key}@{spec.version}" in wanted
        ]
        missing = wanted - {
            key
            for spec in selected
            for key in (
                spec.document_key,
                Path(spec.file).stem,
                f"{spec.document_key}@{spec.version}",
            )
        }
        if missing:
            raise IngestionError(
                "UNKNOWN_DOCUMENT_KEY", f"清单中不存在文档：{', '.join(sorted(missing))}"
            )
        return selected


def load_manifest(path: Path) -> Manifest:
    """Read and validate a manifest file."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestionError("INVALID_MANIFEST", "清单不是合法 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise IngestionError("INVALID_MANIFEST", "清单缺少 documents 数组")

    specs: list[SourceSpec] = []
    for index, raw in enumerate(payload["documents"]):
        if not isinstance(raw, dict):
            raise IngestionError("INVALID_MANIFEST", f"第 {index} 条文档记录不是对象")
        try:
            effective_from = _parse_datetime(raw["effective_from"])
            specs.append(
                SourceSpec(
                    document_key=str(raw["document_key"]),
                    title=str(raw["title"]),
                    doc_type=str(raw["doc_type"]),
                    version=str(raw["version"]),
                    effective_from=effective_from or datetime.now(UTC),
                    effective_to=_parse_datetime(raw.get("effective_to")),
                    locale=str(raw.get("locale", "zh-CN")),
                    region=str(raw.get("region", "CN")),
                    knowledge_base=str(raw["knowledge_base"]),
                    file=str(raw["file"]),
                )
            )
        except KeyError as exc:
            raise IngestionError(
                "INVALID_MANIFEST", f"第 {index} 条文档记录缺少字段 {exc.args[0]}"
            ) from exc
        except ValueError as exc:
            raise IngestionError("INVALID_MANIFEST", f"第 {index} 条文档时间格式非法") from exc

    return Manifest(shop_key=str(payload.get("shop_key", "demo")), documents=tuple(specs))
