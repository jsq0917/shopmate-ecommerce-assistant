import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  __resetClientState,
  getAccessToken,
  request,
  requestRaw,
  setAccessToken,
  setUnauthorizedHandler,
} from '@/api/client'
import { ApiError } from '@/api/errors'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function envelope(data: unknown) {
  return { data, request_id: 'req-1', trace_id: 'trace-1' }
}

function errorEnvelope(status: number, code: string, message: string) {
  return jsonResponse(
    {
      error: { code, message, retryable: false, retry_after_ms: null, details: {} },
      request_id: 'req-1',
      trace_id: 'trace-1',
    },
    status,
  )
}

describe('API client', () => {
  beforeEach(() => {
    __resetClientState()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('成功响应解包 Envelope.data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(envelope({ ok: true }))),
    )
    const data = await request<{ ok: boolean }>('/auth/me')
    expect(data).toEqual({ ok: true })
  })

  it('默认附带 Accept 与 JSON Content-Type', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(envelope(null)))
    vi.stubGlobal('fetch', fetchMock)
    await request('/x', { method: 'POST', body: { a: 1 } })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers.Accept).toBe('application/json')
    expect(headers['Content-Type']).toBe('application/json')
    expect(init.credentials).toBe('include')
  })

  it('内存 token 写入 Bearer 头，auth:false 时不带', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(envelope(null)))
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('token-abc')

    await request('/auth/me')
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer token-abc',
    })

    await request('/auth/login', { auth: false })
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).not.toMatchObject({
      Authorization: expect.anything(),
    })
    expect(getAccessToken()).toBe('token-abc')
  })

  it('自定义头与幂等头合并注入', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(envelope(null)))
    vi.stubGlobal('fetch', fetchMock)
    await request('/returns', {
      method: 'POST',
      body: {},
      idempotencyKey: 'idem-1',
      headers: { 'X-CSRF-Token': 'csrf-1' },
    })
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      'Idempotency-Key': 'idem-1',
      'X-CSRF-Token': 'csrf-1',
    })
  })

  it('查询参数序列化并跳过空值', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse(envelope([])))
    vi.stubGlobal('fetch', fetchMock)
    await request('/products/search', {
      query: { q: '耳机', category: '', brand: undefined, limit: 10, in_stock_only: true },
    })
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('q=%E8%80%B3%E6%9C%BA')
    expect(url).toContain('limit=10')
    expect(url).toContain('in_stock_only=true')
    expect(url).not.toContain('category')
    expect(url).not.toContain('brand')
  })

  it('失败信封转换为 ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => errorEnvelope(409, 'DUPLICATE_REQUEST', '重复提交')))
    await expect(request('/chat/stream', { method: 'POST' })).rejects.toMatchObject({
      code: 'DUPLICATE_REQUEST',
      message: '重复提交',
      status: 409,
    })
    await expect(request('/chat/stream', { method: 'POST' })).rejects.toBeInstanceOf(ApiError)
  })

  it('非信封 404 使用兜底文案', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Not Found' }, 404)))
    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError
    expect(error.code).toBe('NOT_FOUND')
    expect(error.message).not.toContain('trace')
  })

  it('204 返回 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(request('/conversations/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('401 触发静默刷新并原样重试一次', async () => {
    let call = 0
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => {
      call += 1
      return call === 1
        ? errorEnvelope(401, 'UNAUTHENTICATED', '过期')
        : jsonResponse(envelope({ user_id: 'u-1' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('expired-token')
    setUnauthorizedHandler(async () => {
      setAccessToken('fresh-token')
      return true
    })

    const data = await request<{ user_id: string }>('/auth/me')
    expect(data).toEqual({ user_id: 'u-1' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    // 重试请求使用刷新后的 token
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer fresh-token',
    })
  })

  it('刷新失败时 401 不再重试，直接抛错', async () => {
    const fetchMock = vi.fn(async () => errorEnvelope(401, 'UNAUTHENTICATED', '过期'))
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('expired-token')
    setUnauthorizedHandler(async () => false)

    await expect(request('/auth/me')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('auth:false 的公开接口不触发刷新重试', async () => {
    const fetchMock = vi.fn(async () => errorEnvelope(401, 'UNAUTHENTICATED', '过期'))
    vi.stubGlobal('fetch', fetchMock)
    setUnauthorizedHandler(async () => true)
    await expect(request('/auth/login', { auth: false })).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('FormData 不设置 JSON Content-Type', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      jsonResponse(envelope({ document_id: 'd-1' })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()
    form.set('title', '政策')
    await request('/admin/documents', { method: 'POST', body: form })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
    expect(init.body).toBe(form)
  })

  it('requestRaw 检查 ok 并返回响应体', async () => {
    const ok = new Response('stream', { status: 200 })
    vi.stubGlobal('fetch', vi.fn(async () => ok))
    const response = await requestRaw('/chat/stream', { method: 'POST' })
    expect(await response.text()).toBe('stream')
  })

  it('requestRaw 对失败响应抛 ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => errorEnvelope(400, 'VALIDATION_ERROR', '参数不合法')))
    await expect(requestRaw('/chat/stream', { method: 'POST' })).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
    })
  })

  it('fetch 抛错（断线）映射为 NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    await expect(request('/products/search')).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('abort 的 AbortError 原样抛出', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new DOMException('aborted', 'AbortError')
    }))
    await expect(request('/chat/stream', { method: 'POST' })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})
