/**
 * 聊天 SSE 流状态机。
 *
 * 覆盖 docs/06-api.md 第 7 节的约束：
 * - 首个业务事件必须是 meta；终止事件只有一个（done 或 error）；
 * - tool_status 按 tool_name 聚合 started -> succeeded/failed；
 * - delta 按序拼接；done 携带 message_id 与 finish_reason；
 * - 用户主动停止（abort）与网络断线分别呈现不同提示；
 * - 409 REQUEST_IN_PROGRESS / DUPLICATE_REQUEST 在建立流前以 JSON 返回。
 */

import { ref } from 'vue'

import { chatApi } from '@/api/endpoints'
import { ApiError, toApiError } from '@/api/errors'
import type {
  CitationEventData,
  DeltaEventData,
  DoneEventData,
  ErrorEventData,
  MetaEventData,
  MessageCitation,
  ProductCardData,
  ToolStatusEventData,
} from '@/api/types'

export interface TurnToolStatus {
  toolName: string
  status: 'started' | 'succeeded' | 'failed' | 'skipped'
  displayMessage: string | null
  errorCode: string | null
}

export interface TurnState {
  active: boolean
  route: string | null
  toolStatuses: TurnToolStatus[]
  productCards: ProductCardData[]
  citations: MessageCitation[]
  text: string
  messageId: string | null
  finishReason: string | null
  error: ApiError | null
  /** 用户点击了“停止生成”。 */
  stopped: boolean
  /** 建立流之前被服务端拒绝（如重复提交）。 */
  rejected: ApiError | null
}

function initialTurn(): TurnState {
  return {
    active: false,
    route: null,
    toolStatuses: [],
    productCards: [],
    citations: [],
    text: '',
    messageId: null,
    finishReason: null,
    error: null,
    stopped: false,
    rejected: null,
  }
}

function toCitation(data: CitationEventData): MessageCitation {
  return {
    citation_id: data.citation_id,
    label: data.label ?? null,
    document_id: data.document_id,
    version_id: data.version_id,
    chunk_id: data.chunk_id,
    title: data.title,
    heading: data.heading,
    page_no: data.page_no,
    version: data.version,
    effective_from: data.effective_from,
    effective_to: data.effective_to,
    excerpt: data.excerpt,
    as_of: data.as_of,
  }
}

function upsertToolStatus(list: TurnToolStatus[], data: ToolStatusEventData): void {
  if (data.status === 'started') {
    list.push({
      toolName: data.tool_name,
      status: 'started',
      displayMessage: data.display_message,
      errorCode: null,
    })
    return
  }
  const index = [...list]
    .reverse()
    .findIndex((item) => item.toolName === data.tool_name && item.status === 'started')
  if (index >= 0) {
    const target = list[list.length - 1 - index]
    target.status = data.status
    target.errorCode = data.error_code
    if (data.display_message) target.displayMessage = data.display_message
    return
  }
  list.push({
    toolName: data.tool_name,
    status: data.status,
    displayMessage: data.display_message,
    errorCode: data.error_code,
  })
}

export interface SendResult {
  ok: boolean
  /** done / error / stopped / network */
  outcome: 'done' | 'error' | 'stopped' | 'network'
  turn: TurnState
  /** 重复提交：调用方应改为读取历史。 */
  duplicate?: boolean
}

export function useChatStream() {
  const turn = ref<TurnState>(initialTurn())
  let controller: AbortController | null = null

  function resetTurn(): void {
    turn.value = initialTurn()
  }

  async function send(conversationId: string, message: string): Promise<SendResult> {
    resetTurn()
    turn.value.active = true
    controller = new AbortController()

    let outcome: SendResult['outcome'] = 'done'
    try {
      await chatApi.stream(
        {
          conversation_id: conversationId,
          message,
          client_message_id: crypto.randomUUID(),
          signal: controller.signal,
        },
        {
          onEvent: (event) => {
            const data = event.data as Record<string, unknown>
            switch (event.type) {
              case 'meta': {
                const meta = data as unknown as MetaEventData
                turn.value.route = meta.route
                break
              }
              case 'tool_status': {
                upsertToolStatus(turn.value.toolStatuses, data as unknown as ToolStatusEventData)
                break
              }
              case 'product_card': {
                turn.value.productCards.push(data as unknown as ProductCardData)
                break
              }
              case 'citation': {
                turn.value.citations.push(toCitation(data as unknown as CitationEventData))
                break
              }
              case 'delta': {
                const delta = data as unknown as DeltaEventData
                turn.value.text += delta.text
                break
              }
              case 'done': {
                const done = data as unknown as DoneEventData
                turn.value.messageId = done.message_id
                turn.value.finishReason = done.finish_reason
                break
              }
              case 'error': {
                const errorData = data as unknown as ErrorEventData
                outcome = 'error'
                turn.value.error = new ApiError({
                  code: errorData.error_code,
                  message: errorData.user_message,
                  status: 0,
                  retryable: errorData.retryable,
                  retryAfterMs: errorData.retry_after_ms,
                })
                if (errorData.partial_message_id) {
                  turn.value.messageId = errorData.partial_message_id
                }
                break
              }
              default:
                break
            }
          },
        },
      )
    } catch (caught) {
      const error = toApiError(caught)
      if (error.code === 'STREAM_ABORTED' || (caught instanceof DOMException && caught.name === 'AbortError')) {
        turn.value.stopped = true
        outcome = 'stopped'
      } else if (error.code === 'REQUEST_IN_PROGRESS' || error.code === 'DUPLICATE_REQUEST') {
        turn.value.rejected = error
        outcome = 'error'
      } else {
        turn.value.error = error
        outcome = error.code === 'NETWORK_ERROR' ? 'network' : 'error'
      }
    } finally {
      turn.value.active = false
      controller = null
    }

    return { ok: outcome === 'done', outcome, turn: turn.value, duplicate: Boolean(turn.value.rejected) }
  }

  function stop(): void {
    controller?.abort()
  }

  return { turn, send, stop, resetTurn }
}
