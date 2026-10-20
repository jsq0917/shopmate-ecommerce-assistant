import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/errors'
import { sseEvent } from '@/test/factories'

const streamMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/endpoints', () => ({
  chatApi: { stream: streamMock },
}))

import { useChatStream } from './useChatStream'

const CONVERSATION = 'conv-1'

type Consumer = { onEvent: (event: ReturnType<typeof sseEvent>) => void }

/** 让 mock 依次回放事件，模拟一次正常的 SSE 流。 */
function emit(events: ReturnType<typeof sseEvent>[]) {
  return async (_params: unknown, consumer: Consumer) => {
    for (const event of events) consumer.onEvent(event)
  }
}

describe('useChatStream 断线与恢复', () => {
  beforeEach(() => {
    streamMock.mockReset()
  })

  it('正常流：拼接 delta 并记录 done 的结束原因', async () => {
    streamMock.mockImplementation(
      emit([
        sseEvent('meta', { route: 'policy_faq' }, 1),
        sseEvent('delta', { text: '七天' }, 2),
        sseEvent('delta', { text: '无理由 [c1]' }, 3),
        sseEvent('done', { message_id: 'm-1', finish_reason: 'stop' }, 4),
      ]),
    )

    const { turn, send } = useChatStream()
    const result = await send(CONVERSATION, '七天无理由怎么退？')

    expect(result.outcome).toBe('done')
    expect(result.ok).toBe(true)
    expect(turn.value.text).toBe('七天无理由 [c1]')
    expect(turn.value.finishReason).toBe('stop')
    expect(turn.value.error).toBeNull()
    expect(turn.value.active).toBe(false)
  })

  it('连接中断：标记为网络错误且可重试，不吞掉半截内容', async () => {
    streamMock.mockImplementation(async (_params: unknown, consumer: Consumer) => {
      consumer.onEvent(sseEvent('meta', { route: 'policy_faq' }, 1))
      consumer.onEvent(sseEvent('delta', { text: '半句' }, 2))
      throw new ApiError({
        code: 'NETWORK_ERROR',
        message: '网络连接中断，请检查网络后重试。',
        status: 0,
        retryable: true,
      })
    })

    const { turn, send } = useChatStream()
    const result = await send(CONVERSATION, '七天无理由怎么退？')

    expect(result.outcome).toBe('network')
    expect(result.ok).toBe(false)
    expect(turn.value.error?.code).toBe('NETWORK_ERROR')
    expect(turn.value.error?.retryable).toBe(true)
    expect(turn.value.text).toBe('半句')
    expect(turn.value.active).toBe(false)
  })

  it('断线后重试成功：错误清空并展示完整回答', async () => {
    streamMock
      .mockImplementationOnce(async () => {
        throw new ApiError({
          code: 'NETWORK_ERROR',
          message: '网络连接中断，请检查网络后重试。',
          status: 0,
          retryable: true,
        })
      })
      .mockImplementationOnce(
        emit([
          sseEvent('meta', { route: 'policy_faq' }, 1),
          sseEvent('delta', { text: '恢复后的回答' }, 2),
          sseEvent('done', { message_id: 'm-2', finish_reason: 'stop' }, 3),
        ]),
      )

    const { turn, send } = useChatStream()
    const failed = await send(CONVERSATION, '七天无理由怎么退？')
    expect(failed.outcome).toBe('network')

    const retried = await send(CONVERSATION, '七天无理由怎么退？')
    expect(retried.outcome).toBe('done')
    expect(turn.value.error).toBeNull()
    expect(turn.value.text).toBe('恢复后的回答')
  })

  it('服务端 error 事件：转成 ApiError 并保留中文提示', async () => {
    streamMock.mockImplementation(
      emit([
        sseEvent('meta', { route: 'product_discovery' }, 1),
        sseEvent(
          'error',
          {
            error_code: 'UPSTREAM_UNAVAILABLE',
            user_message: '当前无法确认最新信息，请稍后重试或转人工协助。',
            retryable: true,
            retry_after_ms: 3000,
            partial_message_id: null,
            partial_persisted: false,
          },
          2,
        ),
      ]),
    )

    const { turn, send } = useChatStream()
    const result = await send(CONVERSATION, '推荐一款降噪耳机')

    expect(result.outcome).toBe('error')
    expect(turn.value.error?.code).toBe('UPSTREAM_UNAVAILABLE')
    expect(turn.value.error?.message).toContain('无法确认')
    expect(turn.value.error?.retryAfterMs).toBe(3000)
  })

  it('用户主动停止：区分于网络错误，不提示“网络异常”', async () => {
    streamMock.mockImplementation(async (_params: unknown, _consumer: Consumer) => {
      throw new DOMException('The stream was aborted.', 'AbortError')
    })

    const { turn, send } = useChatStream()
    const result = await send(CONVERSATION, '你好')

    expect(result.outcome).toBe('stopped')
    expect(turn.value.stopped).toBe(true)
    expect(turn.value.error).toBeNull()
  })

  it('建立流前的 409 重复请求：标记为 rejected 而非通用错误', async () => {
    streamMock.mockImplementation(async () => {
      throw new ApiError({
        code: 'DUPLICATE_REQUEST',
        message: '这条消息已经提交过，请读取历史记录，不要重复发送。',
        status: 409,
      })
    })

    const { turn, send } = useChatStream()
    const result = await send(CONVERSATION, '你好')

    expect(result.duplicate).toBe(true)
    expect(turn.value.rejected?.code).toBe('DUPLICATE_REQUEST')
  })
})
