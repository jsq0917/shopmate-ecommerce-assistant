"""Heading-aware parent/child chunking.

Chunking is pure and deterministic: identical blocks plus configuration always produce
identical drafts. Page numbers and heading paths survive the split so citations can point
at the original document location.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x3040, 0x30FF),
)

_SENTENCE_BREAK = re.compile(r"(?<=[。！？；!?;])|\n+")
_SOFT_BREAK = re.compile(r"(?<=[，,、：:])")
_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """A contiguous piece of source text with its origin metadata."""

    text: str
    heading_path: tuple[str, ...] = ()
    page_no: int | None = None


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """One chunk ready for persistence; parents have ``parent_index`` unset."""

    chunk_index: int
    role: Literal["parent", "child"]
    text: str
    heading_path: tuple[str, ...]
    page_no: int | None
    parent_index: int | None


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    heading_path: tuple[str, ...]
    page_no: int | None


def is_cjk(char: str) -> bool:
    """Return True when the character belongs to a CJK block."""
    code = ord(char)
    return any(low <= code <= high for low, high in CJK_RANGES)


def estimate_token_count(text: str) -> int:
    """Estimate tokens without shipping a model tokenizer.

    CJK characters count as one token each, latin/digit runs count as one token each.
    The estimate is deliberately conservative and only used for budget warnings.
    """
    cjk = sum(1 for char in text if is_cjk(char))
    latin_runs = len(re.findall(r"[A-Za-z0-9]+", text))
    return cjk + latin_runs


def _clean(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


def _split_sentences(text: str) -> list[str]:
    pieces = [piece.strip() for piece in _SENTENCE_BREAK.split(text)]
    return [piece for piece in pieces if piece]


def _split_oversized(sentence: str, max_chars: int) -> list[str]:
    """Break a sentence that alone exceeds ``max_chars`` at soft punctuation."""
    if len(sentence) <= max_chars:
        return [sentence]
    parts: list[str] = []
    buffer = ""
    for piece in _SOFT_BREAK.split(sentence):
        if not piece:
            continue
        if buffer and len(buffer) + len(piece) > max_chars:
            parts.append(buffer)
            buffer = piece
        else:
            buffer += piece
        while len(buffer) > max_chars:
            parts.append(buffer[:max_chars])
            buffer = buffer[max_chars:]
    if buffer:
        parts.append(buffer)
    return parts


def _units(blocks: list[ParsedBlock], max_chars: int) -> list[_Unit]:
    """Turn blocks into sentence-aligned units no longer than ``max_chars``."""
    units: list[_Unit] = []
    for block in blocks:
        text = _clean(block.text)
        if not text:
            continue
        buffer: list[str] = []
        size = 0
        for sentence in _split_sentences(text):
            for part in _split_oversized(sentence, max_chars):
                if buffer and size + len(part) > max_chars:
                    units.append(_Unit("\n".join(buffer), block.heading_path, block.page_no))
                    buffer = []
                    size = 0
                buffer.append(part)
                size += len(part)
        if buffer:
            units.append(_Unit("\n".join(buffer), block.heading_path, block.page_no))
    return units


def _group(units: list[_Unit], target_chars: int) -> list[list[_Unit]]:
    """Split units into balanced groups near ``target_chars``.

    Balanced grouping avoids the tiny trailing chunk that greedy filling produces, which
    would otherwise create chunks too small to cite meaningfully.
    """
    if not units:
        return []
    total = sum(len(unit.text) for unit in units)
    if total <= target_chars:
        return [units]
    group_count = max(1, min(math.ceil(total / target_chars), len(units)))
    per_group = total / group_count

    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    size = 0
    for index, unit in enumerate(units):
        groups_left = group_count - len(groups)
        units_left = len(units) - index
        can_split = groups_left > 1 and units_left >= groups_left - 1
        if current and can_split and size + len(unit.text) > per_group:
            groups.append(current)
            current = []
            size = 0
        current.append(unit)
        size += len(unit.text)
    if current:
        groups.append(current)
    return groups


def split_parent_child(
    blocks: list[ParsedBlock],
    *,
    parent_chars: int = 1500,
    child_chars: int = 480,
) -> list[ChunkDraft]:
    """Split parsed blocks into parent chunks and their child chunks.

    Parents are filled to ``parent_chars``; children to ``child_chars``. Children never
    cross a parent boundary, and every child carries the page number and heading path of
    its first sentence.
    """
    if parent_chars <= 0 or child_chars <= 0:
        raise ValueError("chunk sizes must be positive")
    if child_chars > parent_chars:
        raise ValueError("child chunk size must not exceed parent chunk size")

    units = _units(blocks, child_chars)
    if not units:
        return []

    drafts: list[ChunkDraft] = []
    index = 0
    for parent_units in _group(units, parent_chars):
        parent_text = "\n".join(unit.text for unit in parent_units)
        parent_index = index
        drafts.append(
            ChunkDraft(
                chunk_index=parent_index,
                role="parent",
                text=parent_text,
                heading_path=parent_units[0].heading_path,
                page_no=parent_units[0].page_no,
                parent_index=None,
            )
        )
        index += 1
        for child_units in _group(parent_units, child_chars):
            drafts.append(
                ChunkDraft(
                    chunk_index=index,
                    role="child",
                    text="\n".join(unit.text for unit in child_units),
                    heading_path=child_units[0].heading_path,
                    page_no=child_units[0].page_no,
                    parent_index=parent_index,
                )
            )
            index += 1
    return drafts


def token_budget_warning(drafts: list[ChunkDraft], parent_chars: int) -> list[str]:
    """Return human-readable warnings for chunks outside the configured budget."""
    warnings: list[str] = []
    for draft in drafts:
        if draft.role == "parent" and len(draft.text) > parent_chars * 2:
            warnings.append(f"parent chunk {draft.chunk_index} is {len(draft.text)} chars")
        if draft.role == "child" and len(draft.text) > parent_chars:
            warnings.append(f"child chunk {draft.chunk_index} is {len(draft.text)} chars")
    return warnings


def average_char_length(drafts: list[ChunkDraft], role: Literal["parent", "child"]) -> float:
    """Return the mean character length of the given chunk role (0 when absent)."""
    lengths = [len(draft.text) for draft in drafts if draft.role == role]
    if not lengths:
        return 0.0
    return math.fsum(lengths) / len(lengths)
