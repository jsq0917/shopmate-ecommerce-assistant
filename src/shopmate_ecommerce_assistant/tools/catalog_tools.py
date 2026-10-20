"""Read-only catalog tools: search, detail, compare and stock.

Every fact returned here is read from PostgreSQL through :class:`CatalogReader`; prices and
quantities are copied as integers (cents / units). The model never supplies identity, and
no input string is ever concatenated into SQL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.domain.catalog.attributes import split_search_attributes
from shopmate_ecommerce_assistant.domain.catalog.compare import build_rows
from shopmate_ecommerce_assistant.domain.catalog.models import SearchCriteria, VariantSnapshot
from shopmate_ecommerce_assistant.domain.catalog.ports import CatalogReader
from shopmate_ecommerce_assistant.domain.catalog.search import (
    MIN_KEYWORD_SCORE,
    matched_reasons,
    merged_attributes,
    rank_hits,
    tokenize_query,
)
from shopmate_ecommerce_assistant.domain.catalog.stock import (
    aggregate_status,
    latest_stock_timestamp,
    stock_status,
    total_available,
)
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.schemas import (
    CheckStockData,
    CheckStockInput,
    CompareProductRef,
    CompareProductsData,
    CompareProductsInput,
    CompareValue,
    GetProductDetailInput,
    ProductCard,
    ProductDetail,
    ProductDetailData,
    ProductStockSummary,
    SearchProductsData,
    SearchProductsInput,
    ToolFailure,
    ToolResult,
    ToolSuccess,
    VariantDetail,
    WarehouseStockItem,
)
from shopmate_ecommerce_assistant.tools.schemas import (
    CompareRow as CompareRowSchema,
)

logger = logging.getLogger(__name__)


GENERIC_VALIDATION_MESSAGE = (
    "请求参数不合法，请检查查询词、类目、品牌、预算、属性或数量是否在允许范围内。"
)
PRODUCT_NOT_FOUND_MESSAGE = "未找到该商品，可能已下架或不属于当前店铺。请重新选择商品。"
VARIANT_NOT_FOUND_MESSAGE = "未找到该商品规格，请重新选择颜色或型号。"
UPSTREAM_MESSAGE = "商品数据暂时无法读取，请稍后重试；如持续失败可转人工协助。"
INTERNAL_MESSAGE = "商品查询出现异常，请稍后重试或转人工协助。"


def _utc_now() -> datetime:
    """Return the current UTC instant (injectable for deterministic tests)."""
    return datetime.now(UTC)


def _validate[T: BaseModel](model: type[T], payload: Any) -> T:
    """Validate a payload against a strict schema, mapping errors to a safe tool error."""
    if isinstance(payload, model):
        return payload
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ToolError(ErrorCode.VALIDATION_ERROR, GENERIC_VALIDATION_MESSAGE) from exc


class CatalogTools:
    """The four stage-6 catalog tools, sharing one shop-scoped reader."""

    def __init__(
        self,
        reader: CatalogReader,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def search_products(self, payload: Any, *, context: ToolContext) -> ToolResult:
        """Search products by keywords, category, brand, budget, attributes and stock."""
        try:
            context.ensure_catalog_read()
            params = _validate(SearchProductsInput, payload)
            tokens = tokenize_query(params.query)
            product_attributes, variant_attributes = split_search_attributes(
                params.attributes or {}
            )

            # Relevance ranking happens in Python, so fetch a wider candidate window when
            # a keyword filter is present; without keywords the SQL order is already final.
            candidate_limit = (
                min(max(params.limit * 5, 20), 100) + 1 if tokens else params.limit + 1
            )

            hits = await self._reader.search(
                shop_id=context.shop_id,
                criteria=SearchCriteria(
                    tokens=tokens,
                    category=params.category,
                    brand=params.brand,
                    budget_min_cents=params.budget_min_cents,
                    budget_max_cents=params.budget_max_cents,
                    product_attributes=product_attributes,
                    variant_attributes=variant_attributes,
                    in_stock_only=params.in_stock_only,
                ),
                limit=candidate_limit,
            )

            truncated = len(hits) > params.limit
            evaluated_at = self._clock()
            ranked = rank_hits(hits, tokens)
            if tokens:
                # A description-only hit on a filler word is not a product match.
                ranked = [item for item in ranked if item.match.score >= MIN_KEYWORD_SCORE]
            ranked = ranked[: params.limit]

            cards: list[ProductCard] = []
            for item in ranked:
                variant = item.hit.variant
                status = stock_status(variant.available_qty)
                cards.append(
                    ProductCard(
                        product_id=item.hit.product.id,
                        variant_id=variant.id,
                        title=item.hit.product.title,
                        brand=item.hit.product.brand,
                        category=item.hit.product.category,
                        sku=variant.sku,
                        price_cents=variant.price_cents,
                        currency=variant.currency,
                        stock_status=status,
                        available_qty=variant.available_qty,
                        attributes=merged_attributes(
                            item.hit.product.attributes, variant.attributes
                        ),
                        matched_reasons=matched_reasons(
                            match=item.match,
                            category_filter=params.category is not None,
                            brand_filter=params.brand is not None,
                            budget_filter=params.budget_min_cents is not None
                            or params.budget_max_cents is not None,
                            attribute_filter=bool(params.attributes),
                            in_stock=status == "in_stock",
                        ),
                        image_url=None,
                        is_synthetic=item.hit.product.is_synthetic,
                        as_of=variant.stock_updated_at or evaluated_at,
                    )
                )

            as_of = max((card.as_of for card in cards), default=evaluated_at)
            data = SearchProductsData(items=cards, truncated=truncated)
            return self._success(context, data, as_of)
        except ToolError as exc:
            return self._failure(context, exc)
        except SQLAlchemyError:
            logger.warning("catalog search failed: database unavailable")
            return self._failure(
                context,
                ToolError(ErrorCode.UPSTREAM_UNAVAILABLE, UPSTREAM_MESSAGE, retryable=True),
            )
        except Exception:
            logger.error("catalog search failed: unexpected error")
            return self._failure(context, ToolError(ErrorCode.INTERNAL_ERROR, INTERNAL_MESSAGE))

    async def get_product_detail(self, payload: Any, *, context: ToolContext) -> ToolResult:
        """Return one product with every SKU, its real price and a stock summary."""
        try:
            context.ensure_catalog_read()
            params = _validate(GetProductDetailInput, payload)

            product = await self._reader.get_product(
                shop_id=context.shop_id, product_id=params.product_id
            )
            if product is None:
                raise ToolError(ErrorCode.PRODUCT_NOT_FOUND, PRODUCT_NOT_FOUND_MESSAGE)

            variants = await self._reader.list_variants(
                shop_id=context.shop_id,
                product_id=params.product_id,
                variant_id=params.variant_id,
            )
            if params.variant_id is not None and not variants:
                raise ToolError(ErrorCode.VARIANT_NOT_FOUND, VARIANT_NOT_FOUND_MESSAGE)

            evaluated_at = self._clock()
            stock_at = latest_stock_timestamp(variants) or evaluated_at
            detail = ProductDetail(
                id=product.id,
                title=product.title,
                description=product.description,
                brand=product.brand,
                category=product.category,
                attributes=dict(product.attributes),
                status=product.status,
                is_synthetic=product.is_synthetic,
                image_url=None,
                stock_summary=ProductStockSummary(
                    available_qty=total_available(variants),
                    stock_status=aggregate_status(variants),
                    updated_at=latest_stock_timestamp(variants),
                ),
                variants=[self._variant_detail(variant) for variant in variants],
            )
            return self._success(context, ProductDetailData(product=detail), stock_at)
        except ToolError as exc:
            return self._failure(context, exc)
        except SQLAlchemyError:
            logger.warning("product detail failed: database unavailable")
            return self._failure(
                context,
                ToolError(ErrorCode.UPSTREAM_UNAVAILABLE, UPSTREAM_MESSAGE, retryable=True),
            )
        except Exception:
            logger.error("product detail failed: unexpected error")
            return self._failure(context, ToolError(ErrorCode.INTERNAL_ERROR, INTERNAL_MESSAGE))

    async def compare_products(self, payload: Any, *, context: ToolContext) -> ToolResult:
        """Compare 2-4 products field by field; missing values are explicitly unknown."""
        try:
            context.ensure_catalog_read()
            params = _validate(CompareProductsInput, payload)

            sources = await self._reader.load_compare_sources(
                shop_id=context.shop_id, product_ids=params.product_ids
            )
            if len(sources) != len(params.product_ids):
                raise ToolError(ErrorCode.PRODUCT_NOT_FOUND, PRODUCT_NOT_FOUND_MESSAGE)

            keys = params.attributes or []
            rows = build_rows(sources, keys)
            data = CompareProductsData(
                products=[
                    CompareProductRef(
                        product_id=source.product_id,
                        title=source.title,
                        variant_id=source.variant_id,
                        variant_title=source.variant_title,
                    )
                    for source in sources
                ],
                rows=[
                    CompareRowSchema(
                        key=row.key,
                        label=row.label,
                        values=[
                            CompareValue(
                                product_id=cell.product_id,
                                known=cell.known,
                                value=cell.value,
                                unit=cell.unit,
                                display=cell.display,
                            )
                            for cell in row.cells
                        ],
                    )
                    for row in rows
                ],
            )

            stamps = [source.stock_updated_at for source in sources]
            known_stamps = [stamp for stamp in stamps if stamp is not None]
            as_of = max(known_stamps) if known_stamps else self._clock()
            return self._success(context, data, as_of)
        except ToolError as exc:
            return self._failure(context, exc)
        except SQLAlchemyError:
            logger.warning("product compare failed: database unavailable")
            return self._failure(
                context,
                ToolError(ErrorCode.UPSTREAM_UNAVAILABLE, UPSTREAM_MESSAGE, retryable=True),
            )
        except Exception:
            logger.error("product compare failed: unexpected error")
            return self._failure(context, ToolError(ErrorCode.INTERNAL_ERROR, INTERNAL_MESSAGE))

    async def check_stock(self, payload: Any, *, context: ToolContext) -> ToolResult:
        """Return the real availability of one SKU across warehouses.

        Insufficient stock is reported through ``is_available=false`` together with the
        true quantity, not as an error envelope: the caller needs the number in order to
        answer truthfully ("仅剩 3 件"), and a failure envelope would hide it.
        """
        try:
            context.ensure_catalog_read()
            params = _validate(CheckStockInput, payload)

            variant = await self._reader.get_variant(
                shop_id=context.shop_id, variant_id=params.variant_id
            )
            if variant is None:
                raise ToolError(ErrorCode.VARIANT_NOT_FOUND, VARIANT_NOT_FOUND_MESSAGE)

            available = variant.available_qty
            data = CheckStockData(
                variant_id=variant.id,
                product_id=variant.product_id,
                sku=variant.sku,
                requested_qty=params.quantity,
                available_qty=available,
                is_available=available is not None and available >= params.quantity,
                stock_status=stock_status(available),
                warehouses=[
                    WarehouseStockItem(
                        warehouse_code=warehouse.warehouse_code,
                        available_qty=warehouse.available_qty,
                        updated_at=warehouse.updated_at,
                    )
                    for warehouse in variant.warehouses
                ],
            )
            as_of = variant.stock_updated_at or self._clock()
            return self._success(context, data, as_of)
        except ToolError as exc:
            return self._failure(context, exc)
        except SQLAlchemyError:
            logger.warning("stock check failed: database unavailable")
            return self._failure(
                context,
                ToolError(ErrorCode.UPSTREAM_UNAVAILABLE, UPSTREAM_MESSAGE, retryable=True),
            )
        except Exception:
            logger.error("stock check failed: unexpected error")
            return self._failure(context, ToolError(ErrorCode.INTERNAL_ERROR, INTERNAL_MESSAGE))

    @staticmethod
    def _variant_detail(variant: VariantSnapshot) -> VariantDetail:
        return VariantDetail(
            id=variant.id,
            sku=variant.sku,
            title=variant.title,
            attributes=dict(variant.attributes),
            price_cents=variant.price_cents,
            currency=variant.currency,
            status=variant.status,
            available_qty=variant.available_qty,
            stock_status=stock_status(variant.available_qty),
            stock_updated_at=variant.stock_updated_at,
        )

    def _success(self, context: ToolContext, data: BaseModel, as_of: datetime) -> ToolSuccess:
        return ToolSuccess(
            tool_call_id=uuid4(),
            data=data.model_dump(mode="json"),
            as_of=as_of,
            trace_id=context.trace_id,
        )

    @staticmethod
    def _failure(context: ToolContext, error: ToolError) -> ToolFailure:
        return ToolFailure(
            tool_call_id=uuid4(),
            error_code=error.code.value,
            user_message=error.user_message,
            retryable=error.retryable,
            retry_after_ms=error.retry_after_ms,
            trace_id=context.trace_id,
        )


__all__ = ["CatalogTools"]
