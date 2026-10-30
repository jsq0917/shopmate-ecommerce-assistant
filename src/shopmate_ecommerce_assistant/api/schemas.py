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

from shopmate_ecommerce_assistant.core.generation import (
    DEFAULT_HISTORY_TURNS,
    MAX_HISTORY_TURNS,
    MAX_TOKENS_CEILING,
)
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


class ConversationGenerationParams(BaseModel):
    """Per-conversation generation overrides (stage 19); every field is optional.

    ``None`` means "not overridden": the ``LLM_*`` environment default applies (for
    ``top_p`` the parameter is simply not sent). Range checks live here so an out-of-range
    value can never be stored; ``max_tokens`` additionally has to stay under the
    operator-controlled ``llm_max_tokens_cap``, which the endpoint enforces.
    """

    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_TOKENS_CEILING)
    history_turns: int | None = Field(default=None, ge=0, le=MAX_HISTORY_TURNS)


class ConversationItem(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    #: Knowledge bases this conversation retrieves from (stage 18).
    #: Empty list = no restriction (every knowledge base visible to the shop).
    knowledge_base_ids: list[UUID] = Field(default_factory=list)
    #: Generation-parameter overrides stored on the conversation (stage 19). Only keys the
    #: user set are present; a missing key/null means "use the environment default".
    generation_params: ConversationGenerationParams = Field(
        default_factory=ConversationGenerationParams
    )


class ConversationListData(BaseModel):
    items: list[ConversationItem]
    next_cursor: str | None = None


class CreateConversationRequest(_Strict):
    title: str | None = Field(default=None, max_length=120)
    #: Optional initial selection; empty keeps the "no restriction" default.
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=20)

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
    #: 本轮商品卡片快照；重开历史会话时前端据此还原卡片。
    product_cards: list[dict[str, Any]] = Field(default_factory=list)
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


class UpdateKnowledgeBasesRequest(_Strict):
    """Replace a conversation's knowledge-base selection.

    ``[]`` is a *meaningful* value: it restores "no restriction" (every visible knowledge
    base). The field is required so a caller cannot clear the selection by omission.
    """

    knowledge_base_ids: list[UUID] = Field(max_length=20)


class UpdateGenerationParamsRequest(_Strict):
    """Merge generation-parameter overrides onto a conversation.

    Merge semantics: an omitted field keeps its stored value, an explicit ``null`` clears
    that override. Sending every field as ``null`` restores the environment defaults.
    """

    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_TOKENS_CEILING)
    history_turns: int | None = Field(default=None, ge=0, le=MAX_HISTORY_TURNS)


class GenerationDefaultsData(BaseModel):
    """Server-side defaults the chat page shows as "currently effective" values."""

    #: Effective default temperature (``LLM_TEMPERATURE``); always a concrete number.
    temperature: float
    #: ``None`` = not sent by default (the provider default applies).
    top_p: float | None = None
    #: ``None`` = not sent by default (``LLM_MAX_TOKENS=0``).
    max_tokens: int | None = None
    #: Default history turns (the pre-stage-19 fixed limit).
    history_turns: int = DEFAULT_HISTORY_TURNS
    #: Hard ceiling for a per-conversation ``max_tokens`` override.
    max_tokens_cap: int


class KnowledgeBaseOption(BaseModel):
    """One knowledge base a chat user may select."""

    id: UUID
    name: str
    locale: str
    region: str


class KnowledgeBaseOptionListData(BaseModel):
    items: list[KnowledgeBaseOption]


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
    #: Snapshot taken when the order was placed; decides self-service return eligibility.
    is_returnable: bool = True


class OrderListItem(BaseModel):
    id: UUID
    order_no: str
    status: str
    total_cents: int
    currency: str
    is_synthetic: bool
    placed_at: datetime
    status_updated_at: datetime
    item_count: int = 0
    first_item_title: str | None = None


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
    paid_at: datetime | None = None
    status_updated_at: datetime
    items: list[OrderItemSummary]


class CreateOrderItemRequest(_Strict):
    variant_id: UUID
    quantity: int = Field(ge=1, le=99)


class CreateOrderRequest(_Strict):
    items: list[CreateOrderItemRequest] = Field(min_length=1, max_length=20)
    shipping_address_masked: str | None = Field(default=None, max_length=240)


class RefundItem(BaseModel):
    id: UUID
    refund_no: str
    order_id: UUID
    order_no: str
    order_item_id: UUID | None
    scope: str
    status: str
    reason_code: str
    amount_cents: int
    note: str | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None


class RefundListData(BaseModel):
    items: list[RefundItem]


class CreateRefundRequest(_Strict):
    order_id: UUID
    reason_code: ReturnReasonCode
    order_item_id: UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class RefundReviewRequest(_Strict):
    approve: bool
    review_note: str | None = Field(default=None, max_length=500)


class SupportReplyRequest(_Strict):
    content: str = Field(min_length=1, max_length=2000)


class SupportReplyData(BaseModel):
    message_id: UUID
    conversation_id: UUID
    created_at: datetime


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


# -- support workbench (docs/06-api.md §12) -----------------------------


class SupportTicketItem(BaseModel):
    ticket_id: UUID
    status: str
    risk_level: str
    primary_reason_code: str
    reason_codes: list[str]
    priority: int
    queue: str
    conversation_id: UUID
    user_reference_masked: str
    assigned_to_masked: str | None
    created_at: datetime
    waiting_seconds: int
    #: False when the conversation behind the ticket no longer exists (soft-deleted),
    #: so no transcript can be opened from the workbench.
    transcript_available: bool = True


class SupportTicketListData(BaseModel):
    items: list[SupportTicketItem]
    next_offset: int | None = None


class SupportTicketDetail(BaseModel):
    ticket_id: UUID
    status: str
    risk_level: str
    primary_reason_code: str
    reason_codes: list[str]
    priority: int
    queue: str
    conversation_id: UUID
    user_reference_masked: str
    assigned_to_masked: str | None
    created_at: datetime
    updated_at: datetime
    waiting_seconds: int
    summary_redacted: str
    expected_response: str
    transcript_available: bool = True
    #: True when the caller is the agent currently holding the ticket. The workbench uses it
    #: to lock reply/resolve/close before the takeover, matching the server-side guard.
    assigned_to_me: bool = False


class SupportTicketPatchRequest(_Strict):
    """``assign`` / ``resolve`` / ``close`` / ``archive`` with action-matched fields."""

    action: Literal["assign", "resolve", "close", "archive"]
    assignee_user_id: UUID | None = None
    resolution_summary: str | None = Field(default=None, max_length=500)
    close_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def _match_action(self) -> SupportTicketPatchRequest:
        if self.action == "assign":
            if self.resolution_summary is not None or self.close_reason is not None:
                raise ValueError("assign 不允许携带 resolution_summary/close_reason")
            return self
        if self.assignee_user_id is not None:
            raise ValueError("只有 assign 可以指定 assignee_user_id")
        if self.action == "resolve":
            summary = (self.resolution_summary or "").strip()
            if not summary:
                raise ValueError("resolve 必须提供 resolution_summary")
            if self.close_reason is not None:
                raise ValueError("resolve 不允许携带 close_reason")
            self.resolution_summary = summary
            return self
        if self.action == "close":
            if self.resolution_summary is not None:
                raise ValueError("close 不允许携带 resolution_summary")
            if self.close_reason is not None:
                self.close_reason = self.close_reason.strip() or None
            return self
        # archive: closing a ticket whose transcript is gone must stay explainable, so the
        # reason is mandatory rather than optional.
        if self.resolution_summary is not None:
            raise ValueError("archive 不允许携带 resolution_summary")
        reason = (self.close_reason or "").strip()
        if not reason:
            raise ValueError("archive 必须提供 close_reason")
        self.close_reason = reason
        return self


class SupportTicketPatchData(BaseModel):
    ticket_id: UUID
    status: str
    assigned_to_masked: str | None
    updated_at: datetime
    request_id: UUID


class SupportConversationMessageItem(BaseModel):
    message_id: UUID
    role: str
    content: str
    is_complete: bool
    citations: list[Any]
    risk: dict[str, Any]
    created_at: datetime


class SupportToolCallItem(BaseModel):
    tool_call_id: UUID
    tool_name: str
    status: str
    latency_ms: int
    result_summary: dict[str, Any]


class SupportHandoffSummary(BaseModel):
    ticket_id: UUID
    status: str
    primary_reason_code: str


class SupportConversationData(BaseModel):
    conversation_id: UUID
    title: str
    owner_reference_masked: str
    target_user_id: UUID
    ticket_id: UUID
    messages: list[SupportConversationMessageItem]
    tool_calls: list[SupportToolCallItem]
    handoff: SupportHandoffSummary | None = None


class QualityLabelRequest(_Strict):
    label: Literal["correct", "incorrect", "needs_knowledge"]
    reason_summary: str | None = Field(default=None, max_length=240)

    @field_validator("reason_summary")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class QualityLabelData(BaseModel):
    message_id: UUID
    label: str


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


class UploadDocumentData(BaseModel):
    document_id: UUID
    version_id: UUID
    ingestion_job_id: UUID
    parse_status: str


class ChunkPatchRequest(_Strict):
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    is_enabled: bool | None = None
    change_reason: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def _at_least_one(self) -> ChunkPatchRequest:
        if self.text is None and self.is_enabled is None:
            raise ValueError("至少提供 text 或 is_enabled 之一")
        if self.text is not None:
            stripped = self.text.strip()
            if not stripped:
                raise ValueError("片段文本不能为空")
            self.text = stripped
        return self


class ChunkPatchData(BaseModel):
    chunk_id: UUID
    version_id: UUID
    text: str
    is_enabled: bool
    content_hash: str
    reindex_required: bool
    updated_at: datetime


class ReindexData(BaseModel):
    ingestion_job_id: UUID
    status: str


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
    "ConversationGenerationParams",
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
    "GenerationDefaultsData",
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
    "UpdateGenerationParamsRequest",
    "UserSummary",
    "VariantDetailItem",
]
