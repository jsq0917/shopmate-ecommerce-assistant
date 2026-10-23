"""Serve the original image a citation was OCR'd from (docs/06-api.md §6.3, stage 20).

Image documents are stored under the controlled knowledge directory, and every chunk
carries ``metadata_jsonb.image.image_url`` pointing at this endpoint. Serving the bytes
through the API rather than a public static mount keeps the existing visibility rule: the
caller must be authenticated, the document must belong to the caller's shop, and the file
path is resolved **inside** the knowledge directory (a stored ``../`` can never escape it).

Only image documents are exposed; asking for a PDF here returns 404 instead of handing out
arbitrary uploads under a route that looks like an image endpoint.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import get_access_context, get_session
from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.knowledge_scope import (
    KnowledgeScopeRepository,
)

router = APIRouter(prefix="/api/v1/knowledge-images", tags=["knowledge"])

IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})


def _resolve_asset_path(source_uri: str) -> Path | None:
    """Resolve a stored ``source_uri`` to a real file inside the knowledge directory.

    Kept synchronous and outside the handler so the blocking ``resolve()``/``is_file()``
    calls do not run inside the event loop's coroutine frame.
    """
    root = Path(paths.KNOWLEDGE_DIR).resolve()
    candidate = (root / PurePosixPath(source_uri)).resolve()
    # ``source_uri`` is written by the ingest pipeline, but it is still treated as data:
    # a tampered row must not become an arbitrary file read.
    if not candidate.is_file() or not candidate.is_relative_to(root):
        return None
    return candidate


@router.get("/{document_id}")
async def get_knowledge_image(
    document_id: UUID,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    """Stream the stored screenshot behind one document of the caller's shop."""
    asset = await KnowledgeScopeRepository(session).document_asset(
        shop_id=context.shop_id, document_id=document_id
    )
    if asset is None or asset.mime_type not in IMAGE_MIME_TYPES:
        raise ToolError(ErrorCode.DOCUMENT_NOT_FOUND, "图片不存在。", retryable=False)

    candidate = _resolve_asset_path(asset.source_uri)
    if candidate is None:
        raise ToolError(ErrorCode.DOCUMENT_NOT_FOUND, "图片文件不存在。", retryable=False)

    return FileResponse(
        path=candidate,
        media_type=asset.mime_type,
        filename=asset.filename,
        headers={"Cache-Control": "private, max-age=300"},
    )


__all__ = ["router"]
