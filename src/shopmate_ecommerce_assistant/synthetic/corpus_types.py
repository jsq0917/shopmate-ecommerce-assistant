"""Shared primitives for the synthetic policy corpus.

The corpus is split across three modules so the generated knowledge base stays
reviewable: this module holds the dataclasses, ``knowledge_corpus.py`` the
original stage-5/7 documents, and ``knowledge_corpus_v2.py`` /
``knowledge_corpus_legacy.py`` the stage-17 expansion (new categories and
superseded versions). Keeping the types here lets the data modules import each
other without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

KB_CN = "policy-cn"
KB_SG = "policy-sg"


@dataclass(frozen=True, slots=True)
class Section:
    """A heading with its paragraphs."""

    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyDoc:
    """One synthetic policy document version."""

    key: str
    title: str
    doc_type: str
    region: str
    knowledge_base: str
    version: str
    effective_from: str
    effective_to: str | None
    file_format: str
    sections: tuple[Section, ...]

    @property
    def filename(self) -> str:
        return f"{self.key}-{self.version}.{self.file_format}"


def _doc(
    key: str,
    title: str,
    *,
    doc_type: str,
    version: str,
    effective_from: str,
    sections: tuple[Section, ...],
    region: str = "CN",
    knowledge_base: str = KB_CN,
    effective_to: str | None = None,
    file_format: str = "md",
) -> PolicyDoc:
    return PolicyDoc(
        key=key,
        title=title,
        doc_type=doc_type,
        region=region,
        knowledge_base=knowledge_base,
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
        file_format=file_format,
        sections=sections,
    )
