/**
 * 前端 DTO：与后端 `src/shopmate_ecommerce_assistant/api/schemas.py` 逐字段对齐。
 *
 * 约定（docs/06-api.md）：
 * - 金额一律整数分 + currency，前端只做展示格式化，禁止推断或补写；
 * - 时间一律 ISO 8601 UTC 字符串，展示时转本地时间；
 * - 未知值必须是 null / unknown，禁止生成看似合理的默认值。
 */

// ---- 通用 ---------------------------------------------------------------

export type Uuid = string

/** 查询参数值类型（与 client.ts 的 RequestOptions.query 一致，定义在此避免循环依赖）。 */
export type QueryValue = string | number | boolean | undefined | null

export interface Envelope<T> {
  data: T
  request_id: string
  trace_id: string
}

export interface ErrorBody {
  code: string
  message: string
  retryable: boolean
  retry_after_ms: number | null
  details: Record<string, unknown>
}

export interface ErrorEnvelope {
  error: ErrorBody
  request_id: string
  trace_id: string
}

export interface Pagination {
  next_cursor?: string | null
  next_offset?: number | null
}

// ---- 认证 ---------------------------------------------------------------

export interface CaptchaData {
  captcha_token: string
  question: string
  expires_in_seconds: number
}

export interface RegisterRequest {
  email: string
  password: string
  captcha_token: string
  captcha_answer: string
}

export interface LoginRequest {
  email: string
  password: string
  captcha_token: string
  captcha_answer: string
}

export interface UserSummary {
  user_id: Uuid
  email: string
  display_name_masked: string | null
  role: UserRole
  shop_id: Uuid
  is_synthetic: boolean
}

export type UserRole = 'shopper' | 'support' | 'admin'

export interface TokenData {
  access_token: string
  token_type: 'bearer'
  expires_in_seconds: number
  user: UserSummary
}

export interface MeData {
  user_id: Uuid
  display_name_masked: string | null
  email: string
  role: UserRole
  shop_id: Uuid
  permissions: string[]
}

// ---- 会话与消息 ---------------------------------------------------------

export interface ConversationItem {
  id: Uuid
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationListData extends Pagination {
  items: ConversationItem[]
}

export interface MessageCitation {
  citation_id: string
  label?: string | null
  document_id: string
  version_id: string
  chunk_id: string
  title: string
  heading: string | null
  page_no: number | null
  version: string
  effective_from: string | null
  effective_to: string | null
  excerpt: string | null
  as_of?: string | null
}

export interface MessageRisk {
  risk_level?: string
  risk_codes?: string[]
  primary_reason_code?: string | null
  handoff_required?: boolean
  notes?: string[]
  [key: string]: unknown
}

export interface MessageItem {
  id: Uuid
  role: 'user' | 'assistant'
  content: string
  route: string | null
  finish_reason: string | null
  citations: MessageCitation[]
  risk: MessageRisk
  /** 本轮商品卡片快照（用于重开历史会话时还原卡片）。 */
  product_cards?: ProductCardBase[]
  is_complete: boolean
  created_at: string
  client_message_id: Uuid | null
}

export interface MessageListData extends Pagination {
  items: MessageItem[]
}

export interface ChatStreamRequest {
  conversation_id: Uuid
  message: string
  client_message_id: Uuid
}

// ---- SSE 事件 -----------------------------------------------------------

export type ChatEventType =
  | 'meta'
  | 'tool_status'
  | 'product_card'
  | 'citation'
  | 'delta'
  | 'done'
  | 'error'

export interface StreamEventEnvelope {
  schema_version: string
  event_id: string
  request_id: string
  sequence: number
  occurred_at: string
  type: ChatEventType
  data: Record<string, unknown>
}

export interface MetaEventData {
  trace_id: string
  conversation_id: string
  user_message_id: string
  route: string
  data_classification: string
  is_synthetic: boolean
  stream_version: string
}

export type ToolStatus = 'started' | 'succeeded' | 'failed' | 'skipped'

export interface ToolStatusEventData {
  tool_call_id: string | null
  tool_name: string
  status: ToolStatus
  display_message: string | null
  latency_ms: number | null
  error_code: string | null
}

export type StockStatus = 'in_stock' | 'out_of_stock' | 'unknown'

/** 商品卡片公共字段：SSE product_card 事件与商品搜索结果共用。 */
export interface ProductCardBase {
  product_id: Uuid
  variant_id: Uuid
  title: string
  /** 品类：用于前端生成稳定的占位封面。 */
  category?: string | null
  image_url: string | null
  price_cents: number
  currency: string
  stock_status: StockStatus
  available_qty: number | null
  attributes: Record<string, unknown>
  matched_reasons: string[]
  is_synthetic: boolean
  as_of: string | null
}

/** SSE `product_card` 事件 payload（docs/06-api.md §7）。 */
export interface ProductCardData extends ProductCardBase {
  source?: string
}

/** GET /products/search 返回的商品卡片。 */
export interface ProductCardItem extends ProductCardBase {
  brand: string | null
  category: string
  sku: string
  as_of: string
}

export interface CitationEventData {
  citation_id: string
  label?: string | null
  document_id: string
  version_id: string
  chunk_id: string
  title: string
  heading: string | null
  page_no: number | null
  version: string
  effective_from: string | null
  effective_to: string | null
  excerpt: string | null
  as_of: string | null
}

export interface DeltaEventData {
  message_id: string
  index: number
  text: string
}

export interface DoneEventData {
  message_id: string
  finish_reason: 'stop' | 'refusal' | 'handoff' | 'cancelled' | string
  usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null
  latency_ms: number | null
  persisted: boolean
  message_is_complete: boolean
}

export interface ErrorEventData {
  error_code: string
  user_message: string
  retryable: boolean
  retry_after_ms: number | null
  partial_message_id: string | null
  partial_persisted: boolean
}

// ---- 商品 ---------------------------------------------------------------
// 注意：ProductCardBase / ProductCardData / ProductCardItem 定义在 SSE 事件段之后
// （见上文"商品卡片公共字段"注释处），此处仅保留搜索与比较相关类型。

export interface ProductSearchData extends Pagination {
  items: ProductCardItem[]
  as_of: string
  is_synthetic: boolean
}

export interface ProductSearchParams {
  q?: string
  category?: string
  brand?: string
  budget_min_cents?: number
  budget_max_cents?: number
  in_stock_only?: boolean
  limit?: number
  /** 索引签名：查询参数 DTO 直接透传给 URLSearchParams。 */
  [key: string]: QueryValue | undefined
}

export interface VariantDetailItem {
  id: Uuid
  sku: string
  title: string
  attributes: Record<string, unknown>
  price_cents: number
  currency: string
  status: string
  available_qty: number | null
  stock_status: StockStatus
  stock_updated_at: string | null
}

export interface ProductDetailItem {
  id: Uuid
  title: string
  description: string | null
  brand: string | null
  category: string
  attributes: Record<string, unknown>
  status: string
  is_synthetic: boolean
  image_url: string | null
  stock_summary: Record<string, unknown>
  variants: VariantDetailItem[]
}

export interface ProductDetailData {
  product: ProductDetailItem
  as_of: string
}

export interface CompareValueItem {
  product_id: Uuid
  known: boolean
  value: boolean | number | string | null
  unit: string | null
  display: string
}

export interface CompareRowItem {
  key: string
  label: string
  values: CompareValueItem[]
}

export interface CompareProductRefItem {
  product_id: Uuid
  title: string
  variant_id: Uuid | null
  variant_title: string | null
}

/** POST /products/compare 请求体：product_ids 2-4 个，attributes 可选。 */
export interface CompareRequest {
  product_ids: Uuid[]
  attributes?: string[]
}

/**
 * 默认比较维度（与后端 DEFAULT_COMPARE_KEYS 对齐的结构性维度，非业务数值）。
 * 后端 compare 工具要求 attributes 非空，故前端显式携带；
 * 展示值一律以响应 rows 为准，前端不推断。
 */
export const DEFAULT_COMPARE_ATTRIBUTES = ['price', 'brand', 'category', 'stock_status'] as const

export interface CompareData {
  products: CompareProductRefItem[]
  rows: CompareRowItem[]
  as_of: string
}

// ---- 订单与物流 ---------------------------------------------------------

export interface OrderItemSummary {
  id: Uuid
  sku: string
  title: string
  quantity: number
  unit_price_cents: number
  status: string
  is_returnable: boolean
}

export interface OrderListItem {
  id: Uuid
  order_no: string
  status: string
  total_cents: number
  currency: string
  is_synthetic: boolean
  placed_at: string
  status_updated_at: string
  item_count: number
  first_item_title: string | null
}

export interface OrderListData extends Pagination {
  items: OrderListItem[]
}

export interface OrderDetailData {
  id: Uuid
  order_no: string
  status: string
  total_cents: number
  currency: string
  is_synthetic: boolean
  placed_at: string
  paid_at: string | null
  status_updated_at: string
  items: OrderItemSummary[]
}

export interface CreateOrderItemRequest {
  variant_id: Uuid
  quantity: number
}

export interface CreateOrderRequest {
  items: CreateOrderItemRequest[]
  shipping_address_masked?: string | null
}

// ---- 退款 ---------------------------------------------------------------

export type RefundStatus = 'requested' | 'approved' | 'rejected' | 'completed'

export interface RefundItem {
  id: Uuid
  refund_no: string
  order_id: Uuid
  order_no: string
  order_item_id: Uuid | null
  scope: 'order' | 'item' | string
  status: RefundStatus
  reason_code: string
  amount_cents: number
  note: string | null
  review_note: string | null
  created_at: string
  updated_at: string
  reviewed_at: string | null
}

export interface RefundListData extends Pagination {
  items: RefundItem[]
}

export interface CreateRefundRequest {
  order_id: Uuid
  reason_code: ReturnReasonCode
  order_item_id?: Uuid | null
  note?: string | null
}

export interface RefundReviewRequest {
  approve: boolean
  review_note?: string | null
}

export interface ShipmentEventItem {
  status: string
  description: string
  occurred_at: string
}

export interface ShipmentData {
  order_id: Uuid
  shipment_id: Uuid
  carrier: string
  tracking_no_masked: string
  status: string
  is_synthetic: boolean
  shipped_at: string | null
  estimated_delivery_at: string | null
  delivered_at: string | null
  status_updated_at: string
  events: ShipmentEventItem[]
}

// ---- 退货 ---------------------------------------------------------------

export type ReturnReasonCode =
  | 'SIZE_OR_FIT'
  | 'NO_LONGER_NEEDED'
  | 'DAMAGED_ON_ARRIVAL'
  | 'WRONG_ITEM'
  | 'QUALITY_ISSUE'
  | 'OTHER'

export interface ReturnEligibilityRequest {
  order_id: Uuid
  order_item_id: Uuid
  reason_code: ReturnReasonCode
}

export type ReturnDecision =
  | 'eligible'
  | 'ineligible'
  | 'needs_clarification'
  | 'needs_manual_review'

export interface ReturnEligibilityData {
  decision: ReturnDecision | string
  decision_code: string
  error_code: string | null
  eligible: boolean
  needs_clarification: boolean
  needs_manual_review: boolean
  can_create_return_request: boolean
  handoff_required: boolean
  matched_rule_codes: string[]
  deadline_at: string | null
  required_materials: string[]
  next_action: string
  eligibility_token: string | null
  eligibility_expires_at: string | null
  rule_version: string
  evaluated_at: string
}

export interface CreateReturnRequest {
  order_id: Uuid
  order_item_id: Uuid
  reason_code: ReturnReasonCode
  eligibility_token: string
  confirmed: boolean
}

export interface CreateReturnData {
  return_request_id: Uuid
  status: 'submitted'
  submitted_at: string
  review_required: boolean
  required_materials: string[]
  next_action: string
  refund_status: 'not_created'
  notice: string
  idempotent_replay: boolean
}

// ---- 人工工单（消费者侧） ----------------------------------------------

export interface HandoffListItem {
  ticket_id: Uuid
  status: string
  risk_level: string
  primary_reason_code: string
  reason_codes: string[]
  priority: number
  queue: string
  summary_redacted: string
  expected_response: string
  created_at: string
  updated_at: string
}

export interface HandoffListData extends Pagination {
  items: HandoffListItem[]
}

export interface CreateHandoffRequest {
  conversation_id: Uuid
  reason_code: string
  summary_redacted: string
}

export interface CreateHandoffData {
  ticket_id: Uuid
  status: 'open'
  risk_level: string
  priority: number
  queue: string
  primary_reason_code: string
  reason_codes: string[]
  expected_response: string
  created_at: string
  idempotent_replay: boolean
}

// ---- 客服工作台（docs/06-api.md 第 12 节契约） --------------------------

export type TicketStatus = 'open' | 'assigned' | 'resolved' | 'closed'

export interface SupportTicketListItem {
  ticket_id: Uuid
  status: TicketStatus
  risk_level: string
  primary_reason_code: string
  reason_codes: string[]
  priority: number
  queue: string
  conversation_id: Uuid
  user_reference_masked: string
  assigned_to_masked: string | null
  created_at: string
  waiting_seconds: number
}

export interface SupportTicketListData extends Pagination {
  items: SupportTicketListItem[]
}

export interface SupportTicketDetail {
  ticket_id: Uuid
  status: TicketStatus
  risk_level: string
  primary_reason_code: string
  reason_codes: string[]
  priority: number
  queue: string
  conversation_id: Uuid
  user_reference_masked: string
  assigned_to_masked: string | null
  created_at: string
  updated_at: string
  summary_redacted: string
  expected_response: string
}

export interface SupportConversationMessage {
  message_id: Uuid
  role: 'user' | 'assistant'
  content: string
  is_complete: boolean
  citations: MessageCitation[]
  risk: MessageRisk
  created_at: string
}

export interface SupportToolCall {
  tool_call_id: Uuid
  tool_name: string
  status: string
  latency_ms: number | null
  result_summary: Record<string, unknown>
}

export interface SupportConversation {
  conversation_id: Uuid
  title: string
  owner_reference_masked: string
  target_user_id: Uuid
  ticket_id: Uuid
  messages: SupportConversationMessage[]
  tool_calls: SupportToolCall[]
  handoff: {
    ticket_id: Uuid
    status: string
    primary_reason_code: string
  } | null
}

export interface SupportReplyRequest {
  content: string
}

export interface SupportReplyData {
  message_id: Uuid
  conversation_id: Uuid
  created_at: string
}

export interface SupportTicketPatch {
  action: 'assign' | 'resolve' | 'close'
  assignee_user_id?: Uuid | null
  resolution_summary?: string | null
  close_reason?: string | null
}

export interface SupportTicketPatchResult {
  ticket_id: Uuid
  status: TicketStatus
  assigned_to_masked: string | null
  updated_at: string
  request_id: string
}

export interface QualityLabelRequest {
  label: 'correct' | 'incorrect' | 'needs_knowledge'
  reason_summary?: string | null
}

// ---- 管理端（docs/06-api.md 第 13 节契约） ------------------------------

export interface KnowledgeBaseItem {
  id: Uuid
  name: string
  locale: string
  region: string
  status: string
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseListData extends Pagination {
  items: KnowledgeBaseItem[]
}

export interface CreateKnowledgeBaseRequest {
  name: string
  locale?: string
  region?: string
}

export type DocumentType =
  | 'policy'
  | 'faq'
  | 'manual'
  | 'warranty'
  | 'invoice'
  | 'shipping'
  | 'other'

export interface DocumentListItem {
  document_id: Uuid
  title: string
  doc_type: string
  knowledge_base_id: Uuid
  status: string
  locale: string
  region: string
  current_version_id: Uuid | null
  current_version: string | null
  parse_status: string | null
  effective_from: string | null
  effective_to: string | null
  updated_at: string
  is_synthetic: boolean
}

export interface DocumentListData extends Pagination {
  items: DocumentListItem[]
}

export interface UploadDocumentRequest {
  knowledge_base_id: Uuid
  title: string
  doc_type: DocumentType
  locale: string
  region: string
  effective_from: string
  effective_to?: string | null
  file: File
}

export interface UploadDocumentData {
  document_id: Uuid
  version_id: Uuid
  ingestion_job_id: Uuid
  parse_status: string
}

export interface ChunkListItem {
  chunk_id: Uuid
  document_id: Uuid
  version_id: Uuid
  chunk_index: number
  heading_path: string[]
  page_no: number | null
  text: string
  token_count: number
  is_enabled: boolean
  updated_at: string
}

export interface ChunkListData extends Pagination {
  items: ChunkListItem[]
}

export interface ChunkPatchRequest {
  text?: string
  is_enabled?: boolean
  change_reason?: string
}

export interface ChunkPatchResult {
  chunk_id: Uuid
  version_id: Uuid
  text: string
  is_enabled: boolean
  content_hash: string
  reindex_required: boolean
  updated_at: string
}

export interface EvalRunItem {
  eval_run_id: Uuid
  dataset_name: string
  dataset_version: string
  status: string
  metrics: Record<string, unknown>
  created_by: Uuid | null
  created_at: string
  updated_at: string
}

export interface EvalRunListData extends Pagination {
  items: EvalRunItem[]
}

export interface CreateEvalRunRequest {
  dataset_name: string
  dataset_version: string
  config_profile_id?: Uuid | null
  seed?: number | null
}

export interface CreateEvalRunData {
  eval_run_id: Uuid
  status: 'queued'
  created_at: string
}

export interface ModelProfileItem {
  profile_id: string
  model_name: string
  provider: string
  supports_structured_tools: boolean
  is_synthetic: boolean
}

export interface ModelProfileListData {
  items: ModelProfileItem[]
}

// ---- 系统 ---------------------------------------------------------------

export interface SystemMetaData {
  environment: string
  data_classification: 'synthetic'
  is_synthetic: boolean
  notice: string
}
