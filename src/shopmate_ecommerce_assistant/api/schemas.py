"""Request and response schemas for the stage-10 REST API.

Strict ``extra="forbid"`` on request bodies so unknown fields — especially identity fields
like ``shop_id``, ``user_id`` or ``role`` — are rejected instead of being honoured.
Amounts stay integer cents and timestamps stay ISO-8601 UTC.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopmate_ecommerce_assistant.db.models.enums import ReturnReasonCode

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# -- auth ---------------------------------------------------------------


class CaptchaData(BaseModel):
    captcha_token: str
    question: str
    expires_in_seconds: int


class RegisterRequest(_Strict):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    captcha_token: str = Field(min_length=8)
    captcha_answer: str = Field(min_length=1, max_length=16)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        stripped = value.strip().lower()
        if not _EMAIL.match(stripped):
            raise ValueError("邮箱格式不正确")
        return stripped


class LoginRequest(_Strict):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    captcha_token: str = Field(min_length=8)
    captcha_answer: str = Field(min_length=1, max_length=16)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        stripped = value.strip().lower()
        if not _EMAIL.match(stripped):
            raise ValueError("邮箱格式不正确")
        return stripped


class UserSummary(BaseModel):
    user_id: UUID
    email: str
    display_name_masked: str | None
    role: str
    shop_id: UUID
    is_synthetic: bool


class TokenData(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    user: UserSummary


class MeData(BaseModel):
    user_id: UUID
    display_name_masked: str | None
    email: str
    role: str
    shop_id: UUID
    permissions: list[str]


class LogoutData(BaseModel):
    logged_out: Literal[True] = True


# -- conversations ------------------------------------------------------


class ConversationItem(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListData(BaseModel):
    items: list[ConversationItem]
    next_cursor: str | None = None


class CreateConversationRequest(_Strict):
    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RenameConversationRequest(_Strict):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("标题不能为空")
        return stripped


class MessageItem(BaseModel):
    id: UUID
    role: str
    content: str
    route: str | None = None
    finish_reason: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    risk: dict[str, Any] = Field(default_factory=dict)
    is_complete: bool
    created_at: datetime
    client_message_id: UUID | None = None


class MessageListData(BaseModel):
    items: list[MessageItem]
    next_cursor: str | None = None


# -- chat ---------------------------------------------------------------


class ChatStreamRequest(_Strict):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("消息不能为空")
        return stripped


# -- catalog ------------------------------------------------------------

StockStatus = Literal["in_stock", "out_of_stock", "unknown"]


class ProductCardItem(BaseModel):
    product_id: UUID
    variant_id: UUID
    title: str
    brand: str | None
    category: str
    sku: str
    price_cents: int
    currency: str
    stock_status: StockStatus
    available_qty: int | None
    attributes: dict[str, Any]
    matched_reasons: list[str]
    image_url: str | None = None
    is_synthetic: bool
    as_of: datetime


class ProductSearchData(BaseModel):
    items: list[ProductCardItem]
    as_of: datetime
    is_synthetic: bool
    next_cursor: str | None = None


class VariantDetailItem(BaseModel):
    id: UUID
    sku: str
    title: str
    attributes: dict[str, Any]
    price_cents: int
    currency: str
    status: str
    available_qty: int | None
    stock_status: StockStatus
    stock_updated_at: datetime | None


class ProductDetailItem(BaseModel):
    id: UUID
    title: str
    description: str | None
    brand: str | None
    category: str
    attributes: dict[str, Any]
    status: str
    is_synthetic: bool
    image_url: str | None = None
    stock_summary: dict[str, Any]
    variants: list[VariantDetailItem]


class ProductDetailData(BaseModel):
    product: ProductDetailItem
    as_of: datetime


class CompareValueItem(BaseModel):
    product_id: UUID
    known: bool
    value: bool | int | float | str | None
    unit: str | None
    display: str


class CompareRowItem(BaseModel):
    key: str
    label: str
    values: list[CompareValueItem]


class CompareProductRefItem(BaseModel):
    product_id: UUID
    title: str
    variant_id: UUID | None
    variant_title: str | None


class CompareData(BaseModel):
    products: list[CompareProductRefItem]
    rows: list[CompareRowItem]
    as_of: datetime


class CompareRequest(_Strict):
    product_ids: list[UUID] = Field(min_length=2, max_length=4)
    attributes: list[str] = Field(default_factory=list)

    @field_validator("product_ids")
    @classmethod
    def _unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("商品 ID 不能重复")
        return value


# -- orders -------------------------------------------------------------


class OrderItemSummary(BaseModel):
    id: UUID
    sku: str
    title: str
    quantity: int
    unit_price_cents: int
    status: str


class OrderListItem(BaseModel):
    id: UUID
    order_no: str
    status: str
    total_cents: int
    currency: str
    is_synthetic: bool
    placed_at: datetime
    status_updated_at: datetime


class OrderListData(BaseModel):
    items: list[OrderListItem]
    next_offset: int | None = None


class OrderDetailData(BaseModel):
    id: UUID
    order_no: str
    status: str
    total_cents: int
    currency: str
    is_synthetic: bool
    placed_at: datetime
    status_updated_at: datetime
    items: list[OrderItemSummary]


class ShipmentEventItem(BaseModel):
    status: str
    description: str
    occurred_at: datetime


class ShipmentData(BaseModel):
    order_id: UUID
    shipment_id: UUID
    carrier: str
    tracking_no_masked: str
    status: str
    is_synthetic: bool
    shipped_at: datetime | None
    estimated_delivery_at: datetime | None
    delivered_at: datetime | None
    status_updated_at: datetime
    events: list[ShipmentEventItem]


# -- returns ------------------------------------------------------------


class ReturnEligibilityRequest(_Strict):
    order_id: UUID
    order_item_id: UUID
    reason_code: ReturnReasonCode


class ReturnEligibilityData(BaseModel):
    decision: str
    decision_code: str
    error_code: str | None
    eligible: bool
    needs_clarification: bool
    needs_manual_review: bool
    can_create_return_request: bool
    handoff_required: bool
    matched_rule_codes: list[str]
    deadline_at: datetime | None
    required_materials: list[str]
    next_action: str
    eligibility_token: str | None
    eligibility_expires_at: datetime | None
    rule_version: str
    evaluated_at: datetime


class CreateReturnRequest(_Strict):
    order_id: UUID
    order_item_id: UUID
    reason_code: ReturnReasonCode
    eligibility_token: str = Field(min_length=16, max_length=4096)
    confirmed: bool

    @model_validator(mode="after")
    def _confirmed(self) -> CreateReturnRequest:
        if not self.confirmed:
            raise ValueError("提交退货申请需要明确确认")
        return self


class CreateReturnData(BaseModel):
    return_request_id: UUID
    status: Literal["submitted"]
    submitted_at: datetime
    review_required: bool
    required_materials: list[str]
    next_action: str
    refund_status: Literal["not_created"]
    notice: str
    idempotent_replay: bool = False


# -- handoff ------------------------------------------------------------


class HandoffListItem(BaseModel):
    ticket_id: UUID
    status: str
    risk_level: str
    primary_reason_code: str
    reason_codes: list[str]
    priority: int
    queue: str
    summary_redacted: str
    expected_response: str
    created_at: datetime
    updated_at: datetime


class HandoffListData(BaseModel):
    items: list[HandoffListItem]
    next_offset: int | None = None


class CreateHandoffRequest(_Strict):
    conversation_id: UUID
    reason_code: str = Field(min_length=2, max_length=80)
    summary_redacted: str = Field(min_length=1, max_length=500)

    @field_validator("reason_code")
    @classmethod
    def _reason(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("summary_redacted")
    @classmethod
    def _summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("转人工摘要不能为空")
        return stripped


class CreateHandoffData(BaseModel):
    ticket_id: UUID
    status: Literal["open"]
    risk_level: str
    priority: int
    queue: str
    primary_reason_code: str
    reason_codes: list[str]
    expected_response: str
    created_at: datetime
    idempotent_replay: bool = False


# -- admin --------------------------------------------------------------


class KnowledgeBaseItem(BaseModel):
    id: UUID
    name: str
    locale: str
    region: str
    status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListData(BaseModel):
    items: list[KnowledgeBaseItem]
    next_offset: int | None = None


class CreateKnowledgeBaseRequest(_Strict):
    name: str = Field(min_length=1, max_length=160)
    locale: str = Field(default="zh-CN", min_length=2, max_length=16)
    region: str = Field(default="CN", min_length=2, max_length=8)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("知识库名称不能为空")
        return stripped


class DocumentListItem(BaseModel):
    document_id: UUID
    title: str
    doc_type: str
    knowledge_base_id: UUID
    status: str
    locale: str
    region: str
    current_version_id: UUID | None
    current_version: str | None
    parse_status: str | None
    effective_from: datetime | None
    effective_to: datetime | None
    updated_at: datetime
    is_synthetic: bool


class DocumentListData(BaseModel):
    items: list[DocumentListItem]
    next_offset: int | None = None


class ChunkListItem(BaseModel):
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_index: int
    heading_path: list[str]
    page_no: int | None
    text: str
    token_count: int
    is_enabled: bool
    updated_at: datetime


class ChunkListData(BaseModel):
    items: list[ChunkListItem]
    next_offset: int | None = None


class EvalRunItem(BaseModel):
    eval_run_id: UUID
    dataset_name: str
    dataset_version: str
    status: str
    metrics: dict[str, Any]
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class EvalRunListData(BaseModel):
    items: list[EvalRunItem]
    next_offset: int | None = None


class CreateEvalRunRequest(_Strict):
    dataset_name: str = Field(min_length=1, max_length=120)
    dataset_version: str = Field(min_length=1, max_length=40)
    config_profile_id: UUID | None = None
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class CreateEvalRunData(BaseModel):
    eval_run_id: UUID
    status: Literal["queued"]
    created_at: datetime


class ModelProfileItem(BaseModel):
    profile_id: str
    model_name: str
    provider: str
    supports_structured_tools: bool
    is_synthetic: bool = True


class ModelProfileListData(BaseModel):
    items: list[ModelProfileItem]


# -- system -------------------------------------------------------------


class SystemMetaData(BaseModel):
    environment: str
    data_classification: Literal["synthetic"] = "synthetic"
    is_synthetic: bool
    notice: str


__all__ = [
    "CaptchaData",
    "ChatStreamRequest",
    "ChunkListData",
    "ChunkListItem",
    "CompareData",
    "CompareRequest",
    "CompareRowItem",
    "CompareValueItem",
    "CompareProductRefItem",
    "ConversationItem",
    "ConversationListData",
    "CreateConversationRequest",
    "CreateEvalRunData",
    "CreateEvalRunRequest",
    "CreateHandoffData",
    "CreateHandoffRequest",
    "CreateKnowledgeBaseRequest",
    "CreateReturnData",
    "CreateReturnRequest",
    "DocumentListData",
    "DocumentListItem",
    "EvalRunItem",
    "EvalRunListData",
    "HandoffListItem",
    "HandoffListData",
    "KnowledgeBaseItem",
    "KnowledgeBaseListData",
    "LoginRequest",
    "LogoutData",
    "MeData",
    "MessageItem",
    "MessageListData",
    "ModelProfileItem",
    "ModelProfileListData",
    "OrderDetailData",
    "OrderItemSummary",
    "OrderListData",
    "OrderListItem",
    "ProductCardItem",
    "ProductDetailData",
    "ProductDetailItem",
    "ProductSearchData",
    "RegisterRequest",
    "RenameConversationRequest",
    "ReturnEligibilityData",
    "ReturnEligibilityRequest",
    "ShipmentData",
    "ShipmentEventItem",
    "SystemMetaData",
    "TokenData",
    "UserSummary",
    "VariantDetailItem",
]
