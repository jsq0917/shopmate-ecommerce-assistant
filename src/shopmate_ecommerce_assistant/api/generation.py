"""Generation-parameter defaults for the chat page (docs/06-api.md §6.1, stage 19).

The chat page must show the *currently effective* generation parameters, which for an
unset override means the server's ``LLM_*`` environment defaults. Hard-coding those in the
frontend would drift from the deployment, so this read-only endpoint exposes them once per
page load. The values are global configuration, not per-user data; any authenticated user
may read them (same visibility rule as ``GET /knowledge-bases``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from shopmate_ecommerce_assistant.api.deps import (
    get_access_context,
    get_request_ids,
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import GenerationDefaultsData
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.generation import DEFAULT_HISTORY_TURNS
from shopmate_ecommerce_assistant.core.security import AccessContext

router = APIRouter(prefix="/api/v1", tags=["generation"])


@router.get("/generation-defaults", response_model=Envelope[GenerationDefaultsData])
async def get_generation_defaults(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[GenerationDefaultsData]:
    """Return the defaults an unset generation override falls back to.

    ``top_p`` / ``max_tokens`` are ``None`` when the deployment does not send them by
    default (``LLM_MAX_TOKENS=0`` means "provider default"), which the chat page renders as
    "默认" rather than a number. ``max_tokens_cap`` is the hard ceiling a per-conversation
    override may not exceed.
    """
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=GenerationDefaultsData(
            temperature=settings.llm_temperature,
            top_p=None,
            max_tokens=settings.llm_max_tokens or None,
            history_turns=DEFAULT_HISTORY_TURNS,
            max_tokens_cap=settings.llm_max_tokens_cap,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
