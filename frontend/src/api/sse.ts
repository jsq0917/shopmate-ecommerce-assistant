/**
 * SSE 流式读取（POST /api/v1/chat/stream）。
 *
 * - 浏览器 EventSource 无法携带 Authorization 头，因此用 fetch + 手动解析；
 * - 帧格式：`id: N` / `event: <type>` / `data: <单行 JSON>`，空行分帧；
 * - `: keepalive` 注释行不是业务事件，直接忽略；
 * - 断线（读取 rejection）抛出 NETWORK_ERROR；调用方 abort 抛出 AbortError；
 * - 只暴露稳定的七种业务事件（meta/tool_status/product_card/citation/delta/done/error）。
 */

import { ApiError, networkError } from './errors'
import type { ChatEventType, StreamEventEnvelope } from './types'

const EVENT_TYPES: readonly ChatEventType[] = [
  'meta',
  'tool_status',
  'product_card',
  'citation',
  'delta',
  'done',
  'error',
]

/** 把一段文本按空行切分为完整帧，返回剩余不完整部分。 */
export function splitFrames(chunk: string): { frames: string[]; rest: string } {
  const parts = chunk.split('\n\n')
  const rest = parts.pop() ?? ''
  return { frames: parts.filter((frame) => frame.trim().length > 0), rest }
}

/** 解析单帧；注释帧与非法帧返回 null。 */
export function parseFrame(frame: string): StreamEventEnvelope | null {
  const dataLines: string[] = []
  let eventName: string | null = null
  let sawField = false
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.replace(/\r$/, '')
    if (line.startsWith(':')) continue // 注释 / keepalive
    const colon = line.indexOf(':')
    if (colon === -1) continue
    const field = line.slice(0, colon)
    let value = line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    sawField = true
    if (field === 'data') dataLines.push(value)
    else if (field === 'event') eventName = value
  }
  if (!sawField || dataLines.length === 0) return null
  let payload: unknown
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return null
  }
  if (!payload || typeof payload !== 'object') return null
  const envelope = payload as Partial<StreamEventEnvelope>
  if (typeof envelope.type !== 'string') return null
  if (eventName !== null && eventName !== envelope.type) return null
  if (!EVENT_TYPES.includes(envelope.type as ChatEventType)) return null
  if (typeof envelope.sequence !== 'number') return null
  return envelope as StreamEventEnvelope
}

export interface SSEConsumer {
  onEvent: (event: StreamEventEnvelope) => void
}

/**
 * 读取 SSE 响应体并把业务事件转交 `onEvent`。
 * 流正常结束（done/error 后服务端关闭）即 resolve；连接中断抛 ApiError。
 */
export async function consumeSSE(
  response: Response,
  consumer: SSEConsumer,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) {
    throw new ApiError({
      code: 'STREAM_ABORTED',
      message: '未能建立流式连接，请重试。',
      status: 0,
      retryable: true,
    })
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      if (signal?.aborted) {
        throw new DOMException('The stream was aborted.', 'AbortError')
      }
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { frames, rest } = splitFrames(buffer)
      buffer = rest
      for (const frame of frames) {
        const event = parseFrame(frame)
        if (event) consumer.onEvent(event)
      }
    }
    // flush 解码器尾部并处理残留帧
    buffer += decoder.decode()
    const { frames } = splitFrames(buffer)
    for (const frame of frames) {
      const event = parseFrame(frame)
      if (event) consumer.onEvent(event)
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw networkError(error)
  } finally {
    reader.releaseLock()
  }
}
