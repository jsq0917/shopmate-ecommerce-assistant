/**
 * 统一 API client。
 *
 * 设计约束：
 * - 只调用公开 REST API，不直连数据库/向量库；
 * - 成功响应解包 `Envelope.data`；失败统一抛 `ApiError`（稳定错误码 + 中文文案）；
 * - access token 仅保存在内存（Pinia），刷新依赖 HttpOnly refresh cookie + CSRF 头；
 * - 写操作支持 `Idempotency-Key` 请求头；
 * - 401 时经注册的 handler 尝试静默刷新并重试一次（防并发刷新由 store 串行化）。
 */

import { shallowRef } from 'vue'

import { ApiError, apiErrorFromEnvelope, apiErrorFromRaw, networkError, toApiError } from './errors'
import type { Envelope, QueryValue } from './types'

export type { QueryValue }

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// ---- 内存中的 access token（不落 localStorage） --------------------------
//
// 用 shallowRef 而非普通变量：auth store 的 `isAuthenticated` 是一个 computed，
// 只有当这里是可被追踪的响应式引用时，token 变化才能让 computed 失效重算。
// 否则 computed 会把「未登录」的首次求值结果永久缓存，导致登录成功后
// 路由守卫仍判定未认证（用户被弹回登录页）。

const accessToken = shallowRef<string | null>(null)

export function setAccessToken(token: string | null): void {
  accessToken.value = token
}

export function getAccessToken(): string | null {
  return accessToken.value
}

// ---- 401 静默刷新协作者 --------------------------------------------------

type UnauthorizedHandler = () => Promise<boolean>

let unauthorizedHandler: UnauthorizedHandler | null = null

/** 由 auth store 注册：返回 true 表示已刷新令牌，调用方应重试原请求一次。 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

// ---- 请求 ----------------------------------------------------------------

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  query?: Record<string, QueryValue>
  body?: unknown
  /** 是否附带 Bearer 头（默认 true；登录/注册/验证码等公开接口传 false）。 */
  auth?: boolean
  /** 幂等键，写入 `Idempotency-Key` 头。 */
  idempotencyKey?: string
  /** 额外请求头（如刷新令牌时的 `X-CSRF-Token`）。 */
  headers?: Record<string, string>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${BASE_URL}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const serialized = params.toString()
  return serialized ? `${url}?${serialized}` : url
}

function buildHeaders(options: RequestOptions, hasJsonBody: boolean): HeadersInit {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (hasJsonBody) headers['Content-Type'] = 'application/json'
  if (options.auth !== false && accessToken.value) {
    headers.Authorization = `Bearer ${accessToken.value}`
  }
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey
  }
  if (options.headers) {
    Object.assign(headers, options.headers)
  }
  return headers
}

async function readError(response: Response): Promise<ApiError> {
  let raw: unknown = null
  try {
    raw = await response.json()
  } catch {
    raw = null
  }
  if (
    raw &&
    typeof raw === 'object' &&
    'error' in raw &&
    typeof (raw as { error?: unknown }).error === 'object'
  ) {
    const envelope = raw as { error: import('./types').ErrorBody; request_id?: string }
    return apiErrorFromEnvelope(response.status, envelope.error, envelope.request_id ?? null)
  }
  return apiErrorFromRaw(response.status, raw)
}

async function send(options: RequestOptions & { path: string }): Promise<Response> {
  const hasJsonBody = options.body !== undefined && !(options.body instanceof FormData)
  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers: buildHeaders(options, hasJsonBody),
    credentials: 'include',
    signal: options.signal,
  }
  if (options.body instanceof FormData) {
    init.body = options.body
  } else if (hasJsonBody) {
    init.body = JSON.stringify(options.body)
  }
  try {
    return await fetch(buildUrl(options.path, options.query), init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw networkError(error)
  }
}

/** 发起请求并解包 `Envelope<T>.data`。204 返回 undefined。 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const attempt = async (): Promise<Response> => send({ ...options, path })
  let response = await attempt()

  if (response.status === 401 && unauthorizedHandler && options.auth !== false) {
    const refreshed = await unauthorizedHandler()
    if (refreshed) {
      response = await attempt()
    }
  }

  if (!response.ok) {
    throw await readError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  const envelope = (await response.json()) as Envelope<T>
  return envelope.data
}

/** 原始 Response（用于 SSE 流式读取；调用方负责检查 ok 与读流）。 */
export async function requestRaw(path: string, options: RequestOptions = {}): Promise<Response> {
  const response = await send({ ...options, path })
  if (!response.ok) {
    const error = await readError(response)
    throw error
  }
  return response
}

/** 供测试注入：重置模块级 token 与 handler。 */
export function __resetClientState(): void {
  accessToken.value = null
  unauthorizedHandler = null
}

export { toApiError }
