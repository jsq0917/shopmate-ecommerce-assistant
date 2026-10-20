import { describe, expect, it, vi } from 'vitest'

import { consumeSSE, parseFrame, splitFrames } from '@/api/sse'
import { sseEvent, sseResponse, sseText } from '@/test/factories'
import type { StreamEventEnvelope } from '@/api/types'

describe('SSE 帧切分', () => {
  it('按空行分帧并返回不完整残余', () => {
    const { frames, rest } = splitFrames('id: 1\ndata: {"a":1}\n\nid: 2\ndata: {"b":2}')
    expect(frames).toHaveLength(1)
    expect(frames[0]).toContain('"a":1')
    expect(rest).toBe('id: 2\ndata: {"b":2}')
  })

  it('过滤空白帧', () => {
    const { frames } = splitFrames('\n\n\n\ndata: {}\n\n\n')
    expect(frames).toHaveLength(1)
  })
})

describe('SSE 帧解析', () => {
  function frameOf(event: StreamEventEnvelope): string {
    return `id: 1\nevent: ${event.type}\ndata: ${JSON.stringify(event)}`
  }

  it('解析合法业务事件', () => {
    const event = sseEvent('meta', { route: 'policy_faq' }, 1)
    const parsed = parseFrame(frameOf(event))
    expect(parsed?.type).toBe('meta')
    expect(parsed?.sequence).toBe(1)
  })

  it('keepalive 注释帧返回 null', () => {
    expect(parseFrame(': keepalive')).toBeNull()
  })

  it('event 名与 type 不一致时拒绝', () => {
    const event = sseEvent('meta', {}, 1)
    const frame = `id: 1\nevent: delta\ndata: ${JSON.stringify(event)}`
    expect(parseFrame(frame)).toBeNull()
  })

  it('未知事件类型拒绝', () => {
    const frame = 'id: 1\nevent: mystery\ndata: {"type":"mystery","sequence":1}'
    expect(parseFrame(frame)).toBeNull()
  })

  it('缺少 sequence 拒绝', () => {
    const frame = 'id: 1\nevent: delta\ndata: {"type":"delta"}'
    expect(parseFrame(frame)).toBeNull()
  })

  it('非法 JSON 拒绝', () => {
    expect(parseFrame('id: 1\nevent: delta\ndata: {oops')).toBeNull()
  })

  it('兼容 CRLF 行尾', () => {
    const event = sseEvent('delta', { text: 'hi' }, 2)
    const frame = `id: 1\r\nevent: delta\r\ndata: ${JSON.stringify(event)}\r`
    const parsed = parseFrame(frame)
    expect(parsed?.type).toBe('delta')
  })
})

describe('consumeSSE', () => {
  const events: StreamEventEnvelope[] = [
    sseEvent('meta', { route: 'product_fact' }, 1),
    sseEvent('tool_status', { tool_name: 'search_products', status: 'started' }, 2),
    sseEvent('delta', { text: '支持降噪' }, 3),
    sseEvent('done', { message_id: 'm-1', finish_reason: 'stop' }, 4),
  ]

  it('按顺序分发全部业务事件', async () => {
    const onEvent = vi.fn()
    await consumeSSE(sseResponse([sseText(events)]), { onEvent })
    expect(onEvent).toHaveBeenCalledTimes(4)
    expect(onEvent.mock.calls.map((call) => (call[0] as StreamEventEnvelope).type)).toEqual([
      'meta',
      'tool_status',
      'delta',
      'done',
    ])
  })

  it('跨 chunk 的半帧正确缓冲拼接', async () => {
    const text = sseText(events)
    const mid = Math.floor(text.length / 2)
    const onEvent = vi.fn()
    await consumeSSE(sseResponse([text.slice(0, mid), text.slice(mid)]), { onEvent })
    expect(onEvent).toHaveBeenCalledTimes(4)
  })

  it('连接中断抛出 NETWORK_ERROR', async () => {
    const onEvent = vi.fn()
    await expect(
      consumeSSE(brokenResponse(), { onEvent }),
    ).rejects.toMatchObject({ code: 'NETWORK_ERROR', retryable: true })
  })

  it('无响应体时抛出 STREAM_ABORTED', async () => {
    const response = new Response(null, { status: 200 })
    await expect(consumeSSE(response, { onEvent: vi.fn() })).rejects.toMatchObject({
      code: 'STREAM_ABORTED',
    })
  })

  it('调用方 abort 原样抛出 AbortError', async () => {
    const controller = new AbortController()
    // 模拟真实 fetch：abort 时响应体流被中断，read() 以 AbortError 拒绝。
    const body = new ReadableStream<Uint8Array>({
      start(streamController) {
        controller.signal.addEventListener('abort', () => {
          streamController.error(new DOMException('The stream was aborted.', 'AbortError'))
        })
      },
    })
    const response = new Response(body, { status: 200 })
    const promise = consumeSSE(response, { onEvent: vi.fn() }, controller.signal)
    controller.abort()
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })
})

function brokenResponse(): Response {
  const encoder = new TextEncoder()
  const text = sseText([sseEvent('delta', { text: '半句' }, 1)])
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(text))
      controller.error(new TypeError('network error'))
    },
  })
  return new Response(body, { status: 200 })
}
