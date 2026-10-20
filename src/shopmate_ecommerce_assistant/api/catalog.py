"""Product catalog endpoints: search, detail and compare (docs/06-api.md section 8)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    build_tool_context,
    get_access_context,
    get_request_ids,
    get_session,
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    CompareData,
    CompareProductRefItem,
    CompareRequest,
    CompareRowItem,
    CompareValueItem,
    ProductCardItem,
    ProductDetailData,
    ProductDetailItem,
    ProductSearchData,
    VariantDetailItem,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.catalog import CatalogRepository
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.schemas import (
    CompareProductsInput,
    GetProductDetailInput,
    SearchProductsInput,
    ToolFailure,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _failure(exc: ToolError) -> None:
    raise exc


def _raise_failure(result: ToolFailure) -> None:
    try:
        code = ErrorCode(result.error_code or ErrorCode.INTERNAL_ERROR.value)
    except ValueError:
        code = ErrorCode.INTERNAL_ERROR
    raise ToolError(
        code,
        result.user_message,
        retryable=result.retryable,
        retry_after_ms=result.retry_after_ms,
    )


@router.get("/search", response_model=Envelope[ProductSearchData])
async def search_products(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    q: Annotated[str, Query(min_length=1, max_length=200)] = "",
    category: Annotated[str | None, Query(max_length=80)] = None,
    brand: Annotated[str | None, Query(max_length=80)] = None,
    budget_min_cents: Annotated[int | None, Query(ge=0)] = None,
    budget_max_cents: Annotated[int | None, Query(ge=0)] = None,
    in_stock_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> Envelope[ProductSearchData]:
    payload = SearchProductsInput(
        query=q,
        category=category,
        brand=brand,
        budget_min_cents=budget_min_cents,
        budget_max_cents=budget_max_cents,
        in_stock_only=in_stock_only,
        limit=limit,
    )
    request_id, trace_id = get_request_ids(request)
    tools = CatalogTools(CatalogRepository(session))
    tctx = build_tool_context(context, request_id=request_id, trace_id=trace_id)
    result = await tools.search_products(payload, context=tctx)
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    items = (result.data or {}).get("items", []) or []
    cards = [_to_card(item) for item in items]
    as_of = result.as_of
    is_synthetic = all(bool(item.get("is_synthetic", True)) for item in items)
    return Envelope(
        data=ProductSearchData(
            items=cards, as_of=as_of, is_synthetic=is_synthetic, next_cursor=None
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/{product_id}", response_model=Envelope[ProductDetailData])
async def get_product(
    product_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    variant_id: Annotated[UUID | None, Query()] = None,
) -> Envelope[ProductDetailData]:
    request_id, trace_id = get_request_ids(request)
    tools = CatalogTools(CatalogRepository(session))
    tctx = build_tool_context(context, request_id=request_id, trace_id=trace_id)
    result = await tools.get_product_detail(
        GetProductDetailInput(product_id=product_id, variant_id=variant_id), context=tctx
    )
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    product = (result.data or {}).get("product", {}) or {}
    detail = ProductDetailItem(
        id=product.get("id"),
        title=product.get("title"),
        description=product.get("description"),
        brand=product.get("brand"),
        category=product.get("category"),
        attributes=product.get("attributes") or {},
        status=product.get("status"),
        is_synthetic=bool(product.get("is_synthetic", True)),
        image_url=product.get("image_url"),
        stock_summary=product.get("stock_summary") or {},
        variants=[
            VariantDetailItem(
                id=v.get("id"),
                sku=v.get("sku"),
                title=v.get("title"),
                attributes=v.get("attributes") or {},
                price_cents=v.get("price_cents"),
                currency=v.get("currency"),
                status=v.get("status"),
                available_qty=v.get("available_qty"),
                stock_status=v.get("stock_status", "unknown"),
                stock_updated_at=v.get("stock_updated_at"),
            )
            for v in (product.get("variants") or [])
        ],
    )
    return Envelope(
        data=ProductDetailData(product=detail, as_of=result.as_of),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("/compare", response_model=Envelope[CompareData])
async def compare_products(
    body: CompareRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[CompareData]:
    request_id, trace_id = get_request_ids(request)
    tools = CatalogTools(CatalogRepository(session))
    tctx = build_tool_context(context, request_id=request_id, trace_id=trace_id)
    result = await tools.compare_products(
        CompareProductsInput(product_ids=body.product_ids, attributes=body.attributes), context=tctx
    )
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    data = result.data or {}
    products = [
        CompareProductRefItem(
            product_id=p.get("product_id"),
            title=p.get("title"),
            variant_id=p.get("variant_id"),
            variant_title=p.get("variant_title"),
        )
        for p in (data.get("products") or [])
    ]
    rows = [
        CompareRowItem(
            key=r.get("key"),
            label=r.get("label"),
            values=[
                CompareValueItem(
                    product_id=v.get("product_id"),
                    known=v.get("known", False),
                    value=v.get("value"),
                    unit=v.get("unit"),
                    display=v.get("display"),
                )
                for v in (r.get("values") or [])
            ],
        )
        for r in (data.get("rows") or [])
    ]
    return Envelope(
        data=CompareData(products=products, rows=rows, as_of=result.as_of),
        request_id=request_id,
        trace_id=trace_id,
    )


def _to_card(item: dict[str, Any]) -> ProductCardItem:
    return ProductCardItem(
        product_id=item["product_id"],
        variant_id=item["variant_id"],
        title=item["title"],
        brand=item.get("brand"),
        category=item["category"],
        sku=item["sku"],
        price_cents=item["price_cents"],
        currency=item["currency"],
        stock_status=item["stock_status"],
        available_qty=item.get("available_qty"),
        attributes=item.get("attributes") or {},
        matched_reasons=item.get("matched_reasons") or [],
        image_url=item.get("image_url"),
        is_synthetic=bool(item.get("is_synthetic", True)),
        as_of=item.get("as_of"),
    )


__all__ = ["router"]
