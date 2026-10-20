"""Knowledge-version fingerprint used to invalidate the FAQ cache."""

from __future__ import annotations

from datetime import UTC, datetime

from shopmate_ecommerce_assistant.db.repositories.knowledge import (
    KnowledgeVersionRow,
    version_digest_from_rows,
)

NOW = datetime(2026, 10, 19, tzinfo=UTC)


def _row(**overrides: object) -> KnowledgeVersionRow:
    payload: dict[str, object] = {
        "document_id": "doc-1",
        "current_version_id": "ver-1",
        "version": "2026.10.1",
        "document_status": "active",
        "document_updated_at": datetime(2026, 10, 1, tzinfo=UTC),
        "effective_from": datetime(2026, 10, 1, tzinfo=UTC),
        "effective_to": None,
        "parse_status": "ready",
    }
    payload.update(overrides)
    return KnowledgeVersionRow(**payload)  # type: ignore[arg-type]


def test_digest_is_stable_for_the_same_state() -> None:
    first = version_digest_from_rows([_row()], chunk_updated_at=NOW, enabled_chunks=10)
    second = version_digest_from_rows([_row()], chunk_updated_at=NOW, enabled_chunks=10)
    assert first == second
    assert len(first) == 16


def test_new_version_changes_the_digest() -> None:
    before = version_digest_from_rows([_row()])
    after = version_digest_from_rows([_row(current_version_id="ver-2", version="2026.11.1")])
    assert before != after


def test_status_and_window_changes_invalidate_the_digest() -> None:
    baseline = version_digest_from_rows([_row()])
    assert version_digest_from_rows([_row(document_status="inactive")]) != baseline
    assert (
        version_digest_from_rows([_row(effective_to=datetime(2026, 11, 1, tzinfo=UTC))]) != baseline
    )
    assert version_digest_from_rows([_row(parse_status="failed")]) != baseline


def test_chunk_edit_or_disable_changes_the_digest() -> None:
    baseline = version_digest_from_rows([_row()], chunk_updated_at=NOW, enabled_chunks=10)
    assert (
        version_digest_from_rows(
            [_row()], chunk_updated_at=datetime(2026, 10, 2, tzinfo=UTC), enabled_chunks=10
        )
        != baseline
    )
    assert version_digest_from_rows([_row()], chunk_updated_at=NOW, enabled_chunks=9) != baseline


def test_document_order_does_not_matter() -> None:
    first = _row(document_id="doc-a")
    second = _row(document_id="doc-b", current_version_id="ver-2")
    assert version_digest_from_rows([first, second]) == version_digest_from_rows([second, first])
