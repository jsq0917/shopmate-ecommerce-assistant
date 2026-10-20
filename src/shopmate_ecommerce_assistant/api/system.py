"""System metadata endpoint (docs/06-api.md section 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from shopmate_ecommerce_assistant.api.deps import get_request_ids, get_settings_dep
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import SystemMetaData
from shopmate_ecommerce_assistant.core.config import Settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/meta", response_model=Envelope[SystemMetaData])
async def system_meta(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[SystemMetaData]:
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=SystemMetaData(
            environment=settings.app_env,
            data_classification="synthetic",
            is_synthetic=True,
            notice="当前展示合成演示数据，不代表真实经营数据。",
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
