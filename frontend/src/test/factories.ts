/**
 * 测试共享 fixture。字段全部对齐 docs/06-api.md 与后端 schemas；
 * 价格/库存等数值只作为样例数据出现在测试中，不进入产品代码。
 */

import type {
  ConversationGenerationParams,
  ConversationItem,
  GenerationDefaults,
  KnowledgeBaseOption,
  MessageCitation,
  MessageItem,
  ProductCardData,
  StreamEventEnvelope,
  SupportTicketListItem,
} from '@/api/types'

export const CONVERSATION_ID = '11111111-1111-4111-8111-111111111111'
export const CONVERSATION_ID_2 = '22222222-2222-4222-8222-222222222222'
export const KB_CN = '44444444-4444-4444-8444-444444444441'
export const KB_SG = '44444444-4444-4444-8444-444444444442'
export const MESSAGE_ID = '33333333-3333-4333-8333-333333333333'

/** 未覆盖任何参数时的默认形态（stage 19）。 */
export const EMPTY_GENERATION_PARAMS: ConversationGenerationParams = {
  temperature: null,
  top_p: null,
  max_tokens: null,
  history_turns: null,
}

export function conversationFixture(overrides: Partial<ConversationItem> = {}): ConversationItem {
  return {
    id: CONVERSATION_ID,
    title: '耳机咨询',
    created_at: '2026-03-01T09:00:00Z',
    updated_at: '2026-03-01T09:05:00Z',
    knowledge_base_ids: [],
    generation_params: {},
    ...overrides,
  }
}

/** GET /generation-defaults 的返回样例（stage 19）。 */
export function generationDefaultsFixture(
  overrides: Partial<GenerationDefaults> = {},
): GenerationDefaults {
  return {
    temperature: 0.1,
    top_p: null,
    max_tokens: null,
    history_turns: 10,
    max_tokens_cap: 4096,
    ...overrides,
  }
}

/** 对话页知识库多选的候选项（GET /knowledge-bases）。 */
export function knowledgeBaseFixture(
  overrides: Partial<KnowledgeBaseOption> = {},
): KnowledgeBaseOption {
  return {
    id: '44444444-4444-4444-8444-444444444444',
    name: 'policy-cn',
    locale: 'zh-CN',
    region: 'CN',
    ...overrides,
  }
}

export function messageFixture(overrides: Partial<MessageItem> = {}): MessageItem {
  return {
    id: MESSAGE_ID,
    role: 'assistant',
    content: '这款耳机支持主动降噪。',
    route: 'product_fact',
    finish_reason: 'stop',
    citations: [],
    risk: {},
    is_complete: true,
    created_at: '2026-03-01T09:05:00Z',
    client_message_id: null,
    ...overrides,
  }
}

export function citationFixture(overrides: Partial<MessageCitation> = {}): MessageCitation {
  return {
    citation_id: 'cit-1',
    label: '[1]',
    document_id: 'doc-1',
    version_id: 'ver-1',
    chunk_id: 'chunk-1',
    title: '退换货政策',
    heading: '第七条 退货期限',
    page_no: 3,
    version: 'v3',
    effective_from: '2026-01-01T00:00:00Z',
    effective_to: null,
    excerpt: '签收后 7 天内可申请退货。',
    as_of: '2026-03-01T09:05:00Z',
    ...overrides,
  }
}

export function productCardFixture(overrides: Partial<ProductCardData> = {}): ProductCardData {
  return {
    product_id: 'prod-1',
    variant_id: 'var-1',
    title: 'SoundCore Q35 降噪耳机',
    image_url: null,
    price_cents: 29900,
    currency: 'CNY',
    stock_status: 'in_stock',
    available_qty: 12,
    attributes: { color: '黑色' },
    matched_reasons: ['预算匹配'],
    is_synthetic: false,
    as_of: '2026-03-01T09:04:00Z',
    ...overrides,
  }
}

export function supportTicketFixture(
  overrides: Partial<SupportTicketListItem> = {},
): SupportTicketListItem {
  return {
    ticket_id: 'ticket-1',
    status: 'open',
    risk_level: 'medium',
    primary_reason_code: 'USER_REQUESTS_HUMAN',
    reason_codes: ['USER_REQUESTS_HUMAN'],
    priority: 2,
    queue: 'after_sales',
    conversation_id: CONVERSATION_ID,
    user_reference_masked: '用户 138****8888',
    assigned_to_masked: null,
    created_at: '2026-03-01T09:10:00Z',
    waiting_seconds: 95,
    transcript_available: true,
    ...overrides,
  }
}

/** 构造一个 SSE 事件信封。 */
export function sseEvent(
  type: StreamEventEnvelope['type'],
  data: Record<string, unknown>,
  sequence: number,
): StreamEventEnvelope {
  return {
    schema_version: '1.0',
    event_id: `evt-${sequence}`,
    request_id: 'req-1',
    sequence,
    occurred_at: '2026-03-01T09:05:00Z',
    type,
    data,
  }
}

/** 把事件序列渲染为 SSE 帧文本（含 keepalive 注释行）。 */
export function sseText(events: StreamEventEnvelope[]): string {
  return events
    .map((event, index) => {
      const head = `: keepalive\nid: ${index + 1}\nevent: ${event.type}`
      return `${head}\ndata: ${JSON.stringify(event)}\n\n`
    })
    .join('')
}

/** 由字符串数组构造 SSE Response（模拟 fetch 响应体）。 */
export function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

/** 模拟“发了几帧后连接中断”的响应体。 */
export function brokenSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.error(new TypeError('network error'))
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}
