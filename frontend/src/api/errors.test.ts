import { describe, expect, it } from 'vitest'

import {
  ApiError,
  apiErrorFromEnvelope,
  apiErrorFromRaw,
  messageForCode,
  messageForStatus,
  networkError,
  toApiError,
} from '@/api/errors'

describe('API 错误模型', () => {
  it('ApiError 保留稳定错误码与请求 ID', () => {
    const error = new ApiError({
      code: 'RETURN_NOT_ALLOWED',
      message: '该商品不满足退货条件。',
      status: 422,
      retryable: false,
      requestId: 'req-1',
    })
    expect(error.code).toBe('RETURN_NOT_ALLOWED')
    expect(error.status).toBe(422)
    expect(error.retryable).toBe(false)
    expect(error.requestId).toBe('req-1')
    expect(error).toBeInstanceOf(Error)
  })

  it('信封错误使用服务端文案，缺省时回退中文映射', () => {
    const withMessage = apiErrorFromEnvelope(
      409,
      {
        code: 'DUPLICATE_REQUEST',
        message: '这条消息已经提交过。',
        retryable: false,
        retry_after_ms: null,
        details: {},
      },
      'req-2',
    )
    expect(withMessage.message).toBe('这条消息已经提交过。')
    expect(withMessage.retryable).toBe(false)

    const withoutMessage = apiErrorFromEnvelope(
      429,
      { code: 'RATE_LIMITED', message: '', retryable: true, retry_after_ms: 3000, details: {} },
      null,
    )
    expect(withoutMessage.message).toBe(messageForCode('RATE_LIMITED'))
    expect(withoutMessage.retryable).toBe(true)
    expect(withoutMessage.retryAfterMs).toBe(3000)
  })

  it('非信封 404 映射为稳定中文文案', () => {
    const error = apiErrorFromRaw(404, { detail: 'Not Found' })
    expect(error.code).toBe('NOT_FOUND')
    expect(error.message).toBe(messageForStatus(404))
    expect(error.retryable).toBe(false)
    expect(error.details).toEqual({ detail: 'Not Found' })
  })

  it('5xx 非信封错误标记为可重试', () => {
    const error = apiErrorFromRaw(503, null)
    expect(error.code).toBe('HTTP_503')
    expect(error.retryable).toBe(true)
  })

  it('网络错误可重试', () => {
    const error = networkError(new TypeError('Failed to fetch'))
    expect(error.code).toBe('NETWORK_ERROR')
    expect(error.retryable).toBe(true)
    expect(error.status).toBe(0)
  })

  it('toApiError 原样返回 ApiError', () => {
    const original = networkError()
    expect(toApiError(original)).toBe(original)
  })

  it('toApiError 把 AbortError 映射为 STREAM_ABORTED', () => {
    const abort = new DOMException('aborted', 'AbortError')
    const error = toApiError(abort)
    expect(error.code).toBe('STREAM_ABORTED')
    expect(error.retryable).toBe(true)
  })

  it('toApiError 把未知异常包装为 INTERNAL_ERROR', () => {
    const error = toApiError(new Error('boom'))
    expect(error.code).toBe('INTERNAL_ERROR')
    expect(error.details).toEqual({ cause: 'Error' })
  })

  it('未知错误码有中文兜底', () => {
    expect(messageForCode('SOME_NEW_CODE')).toBe('请求失败，请稍后重试。')
    expect(messageForStatus(418)).toBe('请求失败，请稍后重试。')
  })
})
