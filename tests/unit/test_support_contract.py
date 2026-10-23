"""Pure-logic tests for the stage-16 support/admin surface.

No database, no HTTP, no model weights: these cover the parts that must never regress for
free — the ticket state machine table, reference masking, request-body rules, and the
upload gate (size, magic bytes, unsafe names).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from shopmate_ecommerce_assistant.api.admin import _magic_ok, _read_limited, _safe_suffix
from shopmate_ecommerce_assistant.api.schemas import (
    ChunkPatchRequest,
    QualityLabelRequest,
    SupportTicketPatchRequest,
)
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.db.models.enums import HandoffStatus
from shopmate_ecommerce_assistant.db.repositories.support import (
    TRANSITIONS,
    mask_reference,
    queue_for,
)


class _StubUpload:
    """Minimal ``UploadFile`` stand-in: only ``read(size)`` is used by the gate."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    async def read(self, size: int) -> bytes:
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


# ------------------------------------------------------------------ 状态机表


def test_transition_table_matches_the_contract() -> None:
    """§12: assign open/assigned→assigned, resolve assigned→resolved, close resolved→closed."""
    assert TRANSITIONS["assign"][1] is HandoffStatus.ASSIGNED
    assert TRANSITIONS["assign"][0] == frozenset({HandoffStatus.OPEN, HandoffStatus.ASSIGNED})
    assert TRANSITIONS["resolve"][0] == frozenset({HandoffStatus.ASSIGNED})
    assert TRANSITIONS["resolve"][1] is HandoffStatus.RESOLVED
    assert TRANSITIONS["close"][0] == frozenset({HandoffStatus.RESOLVED})
    assert TRANSITIONS["close"][1] is HandoffStatus.CLOSED
    # No action may skip straight from open to resolved/closed.
    for action in ("resolve", "close"):
        assert HandoffStatus.OPEN not in TRANSITIONS[action][0]


def test_queue_names_follow_risk() -> None:
    assert queue_for("high") == "priority_support"
    assert queue_for("critical") == "priority_support"
    assert queue_for("medium") == "standard_support"
    assert queue_for("low") == "standard_support"


# ------------------------------------------------------------------ 脱敏


def test_mask_reference_prefers_the_stored_masked_name() -> None:
    user_id = uuid4()
    assert mask_reference(user_id, "sh****") == "sh****"


def test_mask_reference_never_leaks_the_raw_id() -> None:
    user_id = UUID("11111111-2222-3333-4444-555566667777")
    masked = mask_reference(user_id, None)
    assert masked is not None
    assert str(user_id) not in masked
    assert masked.endswith("77")
    assert masked == mask_reference(user_id, None), "must be stable across calls"
    assert mask_reference(None, None) is None


# ------------------------------------------------------------------ 请求体


def test_assign_rejects_resolution_fields() -> None:
    with pytest.raises(ValidationError):
        SupportTicketPatchRequest(action="assign", resolution_summary="已解决")


def test_resolve_requires_a_summary() -> None:
    with pytest.raises(ValidationError):
        SupportTicketPatchRequest(action="resolve")
    with pytest.raises(ValidationError):
        SupportTicketPatchRequest(action="resolve", resolution_summary="   ")
    body = SupportTicketPatchRequest(action="resolve", resolution_summary="  已解释政策  ")
    assert body.resolution_summary == "已解释政策"


def test_close_accepts_optional_reason_only() -> None:
    assert SupportTicketPatchRequest(action="close").close_reason is None
    trimmed = SupportTicketPatchRequest(action="close", close_reason="  用户满意 ")
    assert trimmed.close_reason == "用户满意"
    with pytest.raises(ValidationError):
        SupportTicketPatchRequest(action="close", resolution_summary="已解决")
    with pytest.raises(ValidationError):
        SupportTicketPatchRequest(
            action="resolve", resolution_summary="x", assignee_user_id=uuid4()
        )


def test_quality_label_enum_and_trimming() -> None:
    assert QualityLabelRequest(label="correct").reason_summary is None
    assert QualityLabelRequest(label="incorrect", reason_summary="   ").reason_summary is None
    with pytest.raises(ValidationError):
        QualityLabelRequest(label="maybe")  # type: ignore[arg-type]


def test_chunk_patch_requires_a_field() -> None:
    with pytest.raises(ValidationError):
        ChunkPatchRequest()
    with pytest.raises(ValidationError):
        ChunkPatchRequest(text="   ")
    assert ChunkPatchRequest(is_enabled=False).is_enabled is False
    assert ChunkPatchRequest(text=" 新文本 ").text == "新文本"


# ------------------------------------------------------------------ 上传门禁


def test_suffix_gate_rejects_traversal_and_unsupported_types() -> None:
    assert _safe_suffix("policy.md") == ".md"
    assert _safe_suffix("POLICY.PDF") == ".pdf"
    # Stage 20: screenshots are offline documents too.
    assert _safe_suffix("policy-shot.PNG") == ".png"
    assert _safe_suffix("policy-shot.jpg") == ".jpg"
    assert _safe_suffix("policy-shot.jpeg") == ".jpeg"
    for name in ("../escape.md", "dir/escape.md", "dir\\escape.md", ""):
        with pytest.raises(ToolError) as excinfo:
            _safe_suffix(name)
        assert excinfo.value.code is ErrorCode.UNSAFE_FILE
    for name in ("payload.exe", "animation.gif", "scan.bmp", "scan.webp"):
        with pytest.raises(ToolError) as excinfo:
            _safe_suffix(name)
        assert excinfo.value.code is ErrorCode.UNSUPPORTED_FILE_TYPE


def test_image_uploads_get_a_lower_size_cap() -> None:
    """The OCR path loads the whole picture in memory, so images are capped tighter."""
    from shopmate_ecommerce_assistant.api.admin import _read_upload_limit, _upload_limit_for
    from shopmate_ecommerce_assistant.rag.ingest import loaders

    assert _upload_limit_for(".png") == min(_read_upload_limit(), loaders.IMAGE_MAX_BYTES)
    assert _upload_limit_for(".md") == _read_upload_limit()


def test_magic_check_rejects_disguised_containers() -> None:
    assert _magic_ok(".pdf", b"%PDF-1.7")
    assert not _magic_ok(".pdf", b"<html>")
    assert _magic_ok(".docx", b"PK\x03\x04rest")
    assert not _magic_ok(".pptx", b"%PDF-1.7")
    assert _magic_ok(".md", b"any text")
    assert _magic_ok(".png", b"\x89PNG\r\n\x1a\n")
    assert not _magic_ok(".png", b"<html>")
    assert _magic_ok(".jpg", b"\xff\xd8\xff\xe0")
    assert not _magic_ok(".jpeg", b"\x89PNG\r\n\x1a\n")


async def test_read_limited_enforces_the_size_cap() -> None:
    payload = b"a" * 5000
    with pytest.raises(ToolError) as excinfo:
        await _read_limited(_StubUpload(payload), limit=1024, suffix=".md")
    assert excinfo.value.code is ErrorCode.FILE_TOO_LARGE

    ok = await _read_limited(_StubUpload(b"# title\n"), limit=1024, suffix=".md")
    assert ok == b"# title\n"


async def test_read_limited_rejects_binary_markdown_and_empty_files() -> None:
    with pytest.raises(ToolError) as excinfo:
        await _read_limited(_StubUpload(b"\x00\x01binary"), limit=1024, suffix=".md")
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_FILE_TYPE

    with pytest.raises(ToolError) as excinfo:
        await _read_limited(_StubUpload(b""), limit=1024, suffix=".md")
    assert excinfo.value.code is ErrorCode.VALIDATION_ERROR


async def test_read_limited_rejects_a_fake_pdf_before_buffering_everything() -> None:
    with pytest.raises(ToolError) as excinfo:
        await _read_limited(_StubUpload(b"not a pdf"), limit=1024, suffix=".pdf")
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_FILE_TYPE
