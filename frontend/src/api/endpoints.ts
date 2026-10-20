/**
 * 类型化端点封装。路径与 docs/06-api.md 一致；客服/管理端中尚未在阶段 10
 * 部署的端点也按同一契约实现，部署后即可直接用。
 */

import { request, requestRaw } from './client'
import { consumeSSE, type SSEConsumer } from './sse'
import { DEFAULT_COMPARE_ATTRIBUTES } from './types'
import type {
  CaptchaData,
  ChatStreamRequest,
  ChunkListData,
  ChunkPatchRequest,
  ChunkPatchResult,
  CompareData,
  CompareRequest,
  ConversationItem,
  ConversationListData,
  CreateEvalRunData,
  CreateEvalRunRequest,
  CreateHandoffData,
  CreateHandoffRequest,
  CreateKnowledgeBaseRequest,
  CreateReturnData,
  CreateReturnRequest,
  DocumentListData,
  DocumentListItem,
  Envelope,
  HandoffListData,
  HandoffListItem,
  KnowledgeBaseItem,
  KnowledgeBaseListData,
  LoginRequest,
  MeData,
  MessageListData,
  ModelProfileListData,
  OrderDetailData,
  OrderListData,
  ProductDetailData,
  ProductSearchData,
  ProductSearchParams,
  QualityLabelRequest,
  RegisterRequest,
  ReturnEligibilityData,
  ReturnEligibilityRequest,
  ShipmentData,
  SupportConversation,
  SupportTicketDetail,
  SupportTicketListData,
  SupportTicketPatch,
  SupportTicketPatchResult,
  SystemMetaData,
  TokenData,
  UploadDocumentData,
  UploadDocumentRequest,
} from './types'

const json = <T>(path: string, options?: Parameters<typeof request>[1]) => request<T>(path, options)

// ---- 认证 ---------------------------------------------------------------

export const authApi = {
  captcha: () => json<CaptchaData>('/auth/captcha', { auth: false }),

  register: (body: RegisterRequest) =>
    json<TokenData | { user_id: string }>('/auth/register', {
      method: 'POST',
      body,
      auth: false,
    }),

  login: (body: LoginRequest) =>
    json<TokenData>('/auth/login', { method: 'POST', body, auth: false }),

  /** 依赖 refresh cookie + X-CSRF-Token 头，轮换后返回新的 access token。 */
  refresh: (csrfToken: string) =>
    json<TokenData>('/auth/refresh', {
      method: 'POST',
      auth: false,
      headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : undefined,
    }),

  logout: () => json<{ logged_out: true }>('/auth/logout', { method: 'POST' }),

  me: () => json<MeData>('/auth/me'),
}

// ---- 会话 ---------------------------------------------------------------

export const conversationsApi = {
  list: (params: { limit?: number; cursor?: string } = {}) =>
    json<ConversationListData>('/conversations', { query: params }),

  create: (title?: string) =>
    json<ConversationItem>('/conversations', { method: 'POST', body: { title } }),

  rename: (id: string, title: string) =>
    json<ConversationItem>(`/conversations/${id}`, { method: 'PATCH', body: { title } }),

  remove: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),

  messages: (id: string, params: { limit?: number; before?: string } = {}) =>
    json<MessageListData>(`/conversations/${id}/messages`, { query: params }),
}

// ---- 聊天（SSE） --------------------------------------------------------

export interface StreamChatParams extends ChatStreamRequest {
  signal?: AbortSignal
}

export const chatApi = {
  /** 建立 SSE 流并把事件转交 consumer；连接中断抛 ApiError。 */
  stream: async (params: StreamChatParams, consumer: SSEConsumer): Promise<void> => {
    const response = await requestRaw('/chat/stream', {
      method: 'POST',
      body: {
        conversation_id: params.conversation_id,
        message: params.message,
        client_message_id: params.client_message_id,
      },
      signal: params.signal,
    })
    await consumeSSE(response, consumer, params.signal)
  },
}

// ---- 商品 ---------------------------------------------------------------

export const productsApi = {
  search: (params: ProductSearchParams = {}) =>
    json<ProductSearchData>('/products/search', { query: params }),

  detail: (productId: string, variantId?: string) =>
    json<ProductDetailData>(`/products/${productId}`, { query: { variant_id: variantId } }),

  compare: (body: CompareRequest) =>
    json<CompareData>('/products/compare', {
      method: 'POST',
      // 后端 compare 工具要求至少一个比较维度：未显式指定时携带默认维度
      body: {
        ...body,
        attributes: body.attributes?.length ? body.attributes : [...DEFAULT_COMPARE_ATTRIBUTES],
      },
    }),
}

// ---- 订单与物流 ---------------------------------------------------------

export const ordersApi = {
  list: (params: { status?: string; limit?: number; offset?: number } = {}) =>
    json<OrderListData>('/orders', { query: params }),

  detail: (orderId: string) => json<OrderDetailData>(`/orders/${orderId}`),

  shipment: (orderId: string) => json<ShipmentData>(`/orders/${orderId}/shipment`),
}

// ---- 退货 ---------------------------------------------------------------

export const returnsApi = {
  eligibility: (body: ReturnEligibilityRequest) =>
    json<ReturnEligibilityData>('/returns/eligibility', { method: 'POST', body }),

  create: (body: CreateReturnRequest, idempotencyKey: string) =>
    json<CreateReturnData>('/returns', { method: 'POST', body, idempotencyKey }),
}

// ---- 人工工单（消费者） -------------------------------------------------

export const handoffApi = {
  list: (params: { limit?: number; offset?: number } = {}) =>
    json<HandoffListData>('/handoff', { query: params }),

  get: (ticketId: string) => json<HandoffListItem>(`/handoff/${ticketId}`),

  create: (body: CreateHandoffRequest, idempotencyKey: string) =>
    json<CreateHandoffData>('/handoff', { method: 'POST', body, idempotencyKey }),
}

// ---- 客服工作台（docs/06-api.md 第 12 节） ------------------------------

export const supportApi = {
  tickets: (params: { status?: string; risk_level?: string; limit?: number } = {}) =>
    json<SupportTicketListData>('/support/tickets', { query: params }),

  ticket: (ticketId: string) => json<SupportTicketDetail>(`/support/tickets/${ticketId}`),

  patchTicket: (ticketId: string, body: SupportTicketPatch) =>
    json<SupportTicketPatchResult>(`/support/tickets/${ticketId}`, { method: 'PATCH', body }),

  conversation: (conversationId: string) =>
    json<SupportConversation>(`/support/conversations/${conversationId}`),

  qualityLabel: (assistantMessageId: string, body: QualityLabelRequest) =>
    json<{ message_id: string; label: string }>(
      `/support/messages/${assistantMessageId}/quality-labels`,
      { method: 'POST', body },
    ),
}

// ---- 管理端（docs/06-api.md 第 13 节） ----------------------------------

export const adminApi = {
  knowledgeBases: () => json<KnowledgeBaseListData>('/admin/knowledge-bases'),

  createKnowledgeBase: (body: CreateKnowledgeBaseRequest) =>
    json<KnowledgeBaseItem>('/admin/knowledge-bases', { method: 'POST', body }),

  documents: (knowledgeBaseId?: string) =>
    json<DocumentListData>('/admin/documents', { query: { knowledge_base_id: knowledgeBaseId } }),

  document: (documentId: string) => json<DocumentListItem>(`/admin/documents/${documentId}`),

  uploadDocument: (body: UploadDocumentRequest) => {
    const form = new FormData()
    form.set('knowledge_base_id', body.knowledge_base_id)
    form.set('title', body.title)
    form.set('doc_type', body.doc_type)
    form.set('locale', body.locale)
    form.set('region', body.region)
    form.set('effective_from', body.effective_from)
    if (body.effective_to) form.set('effective_to', body.effective_to)
    form.set('file', body.file)
    return request<UploadDocumentData>('/admin/documents', { method: 'POST', body: form })
  },

  chunks: (params: { document_id?: string; version_id?: string; limit?: number } = {}) =>
    json<ChunkListData>('/admin/chunks', { query: params }),

  patchChunk: (chunkId: string, body: ChunkPatchRequest) =>
    json<ChunkPatchResult>(`/admin/chunks/${chunkId}`, { method: 'PATCH', body }),

  disableChunk: (chunkId: string) =>
    request<ChunkPatchResult>(`/admin/chunks/${chunkId}`, { method: 'DELETE' }),

  reindexDocument: (documentId: string) =>
    json<{ ingestion_job_id: string; status: string }>(`/admin/documents/${documentId}/reindex`, {
      method: 'POST',
      body: {},
    }),

  evalRuns: () => json<import('./types').EvalRunListData>('/admin/eval/runs'),

  createEvalRun: (body: CreateEvalRunRequest) =>
    json<CreateEvalRunData>('/admin/eval/run', { method: 'POST', body }),

  modelProfiles: () => json<ModelProfileListData>('/admin/model-profiles'),
}

// ---- 系统 ---------------------------------------------------------------

export const systemApi = {
  meta: () => json<SystemMetaData>('/system/meta', { auth: false }),
}

export type { Envelope }
