"""Chunking contract: parent/child hierarchy, metadata and size budgets."""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.rag.chunking import (
    ParsedBlock,
    estimate_token_count,
    split_parent_child,
)


def _long_paragraph(sentence: str, repeat: int) -> str:
    return "".join(sentence for _ in range(repeat))


def test_children_reference_their_parent_and_keep_heading_path() -> None:
    blocks = [
        ParsedBlock(
            text=_long_paragraph("本条规定了退货的第一个条件。", 8),
            heading_path=("政策", "退货条件"),
        ),
        ParsedBlock(
            text=_long_paragraph("本条规定了退货的第二个条件。", 8),
            heading_path=("政策", "退货条件"),
        ),
        ParsedBlock(
            text=_long_paragraph("本条规定了退款的到账时间。", 8),
            heading_path=("政策", "退款"),
        ),
    ]

    drafts = split_parent_child(blocks, parent_chars=1200, child_chars=300)

    parents = [draft for draft in drafts if draft.role == "parent"]
    children = [draft for draft in drafts if draft.role == "child"]
    assert parents, "expected at least one parent chunk"
    assert children, "expected at least one child chunk"

    parent_indexes = {parent.chunk_index for parent in parents}
    for child in children:
        assert child.parent_index in parent_indexes
    assert [draft.chunk_index for draft in drafts] == list(range(len(drafts)))


def test_page_numbers_and_heading_paths_survive_the_split() -> None:
    blocks = [
        ParsedBlock(
            text=_long_paragraph("第一页的条款内容。", 40),
            heading_path=("发票", "开票时效"),
            page_no=1,
        ),
        ParsedBlock(
            text=_long_paragraph("第二页的条款内容。", 40),
            heading_path=("发票", "附录"),
            page_no=2,
        ),
    ]

    drafts = split_parent_child(blocks, parent_chars=600, child_chars=300)

    pages = {draft.page_no for draft in drafts if draft.role == "child"}
    assert pages == {1, 2}
    headings = {draft.heading_path for draft in drafts if draft.role == "child"}
    assert ("发票", "开票时效") in headings
    assert ("发票", "附录") in headings


def test_chunk_sizes_stay_within_the_configured_budget() -> None:
    blocks = [
        ParsedBlock(
            text=_long_paragraph("这是一条用于测试分块长度的政策条款。", 120),
            heading_path=("长文档",),
        ),
    ]

    drafts = split_parent_child(blocks, parent_chars=1500, child_chars=480)
    parents = [draft for draft in drafts if draft.role == "parent"]
    children = [draft for draft in drafts if draft.role == "child"]

    assert len(parents) >= 2
    for parent in parents:
        # Balanced grouping keeps parents close to the 1500-char target without a tail.
        assert 900 <= len(parent.text) <= 2100
    for child in children:
        assert 300 <= len(child.text) <= 700, len(child.text)


def test_child_chunks_do_not_cross_parent_boundaries() -> None:
    blocks = [
        ParsedBlock(
            text=_long_paragraph(f"第{index}节的条款内容需要被正确分组。", 30),
            heading_path=("文档", f"第{index}节"),
        )
        for index in range(6)
    ]

    drafts = split_parent_child(blocks, parent_chars=1200, child_chars=400)
    parents = {draft.chunk_index: draft for draft in drafts if draft.role == "parent"}

    for child in (draft for draft in drafts if draft.role == "child"):
        assert child.parent_index is not None
        parent_text = parents[child.parent_index].text
        assert child.text in parent_text


def test_chunking_is_deterministic() -> None:
    blocks = [
        ParsedBlock(text=_long_paragraph("可复现的分块结果。", 30), heading_path=("文档", "章节")),
        ParsedBlock(
            text=_long_paragraph("第二段内容同样需要稳定。", 20), heading_path=("文档", "章节")
        ),
    ]

    first = split_parent_child(blocks, parent_chars=900, child_chars=320)
    second = split_parent_child(blocks, parent_chars=900, child_chars=320)

    assert first == second


def test_blank_document_produces_no_chunks() -> None:
    blank = [ParsedBlock(text="   \n\n  ")]
    assert split_parent_child(blank, parent_chars=1500, child_chars=480) == []


def test_invalid_configuration_is_rejected() -> None:
    blocks = [ParsedBlock(text="内容", heading_path=())]
    with pytest.raises(ValueError):
        split_parent_child(blocks, parent_chars=300, child_chars=500)


def test_token_estimate_counts_cjk_and_words() -> None:
    assert estimate_token_count("七天无理由") == 5
    assert estimate_token_count("USB-C 充电线") == 5
