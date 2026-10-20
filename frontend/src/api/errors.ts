/**
 * API 错误模型。
 *
 * 规则（docs/06-api.md 第 3.3 / 14 节）：
 * - 客户端只消费稳定的 `code`、中文 `message`、`retryable`、`retry_after_ms`；
 * - 不展示 trace_id、堆栈、SQL 或任何内部细节；
 * - 非信封错误（如 FastAPI 默认 404 `{"detail": ...}`）映射为稳定中文文案。
 */

import type { ErrorBody } from './types'

export type ApiErrorCode = string

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly retryable: boolean
  readonly retryAfterMs: number | null
  readonly details: Record<string, unknown>
  /** 关联请求 ID，仅用于日志，禁止在 UI 中展示。 */
  readonly requestId: string | null

  constructor(options: {
    code: ApiErrorCode
    message: string
    status: number
    retryable?: boolean
    retryAfterMs?: number | null
    details?: Record<string, unknown>
    requestId?: string | null
  }) {
    super(options.message)
    this.name = 'ApiError'
    this.code = options.code
    this.status = options.status
    this.retryable = options.retryable ?? false
    this.retryAfterMs = options.retryAfterMs ?? null
    this.details = options.details ?? {}
    this.requestId = options.requestId ?? null
  }
}

/** 稳定错误码 -> 用户可操作的中文提示（缺省兜底）。 */
const CODE_MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: '登录状态已失效，请重新登录。',
  CSRF_INVALID: '会话校验失败，请重新登录。',
  FORBIDDEN: '当前账号没有执行该操作的权限。',
  VALIDATION_ERROR: '请求参数不合法，请检查后重试。',
  CONVERSATION_NOT_FOUND: '未找到可由当前账号访问的会话。',
  PRODUCT_NOT_FOUND: '未找到该商品，可能已下架。',
  VARIANT_NOT_FOUND: '未找到该商品规格。',
  ORDER_NOT_FOUND: '未找到可由当前账号访问的订单。',
  SHIPMENT_NOT_FOUND: '该订单暂无可查看的物流记录。',
  OUT_OF_STOCK: '库存不足，请调整数量或稍后重试。',
  INVALID_STATE: '当前状态不允许该操作。',
  RETURN_NOT_ALLOWED: '该商品不满足退货条件。',
  RETURN_WINDOW_EXPIRED: '已超过退货期限，无法提交申请。',
  DUPLICATE_RETURN: '已存在有效的退货申请，请勿重复提交。',
  MANUAL_REVIEW_REQUIRED: '该情况需要人工审核，已为你转接客服。',
  LOW_CONFIDENCE: '暂时无法理解你的问题，请补充更多信息。',
  CONFIRMATION_REQUIRED: '提交退货申请需要明确确认。',
  ELIGIBILITY_EXPIRED: '退货资格校验已过期，请重新检查。',
  IDEMPOTENCY_CONFLICT: '相同的幂等键对应了不同的请求，请勿重复提交。',
  IDEMPOTENCY_IN_PROGRESS: '相同请求正在处理中，请稍后查看结果。',
  REQUEST_IN_PROGRESS: '上一条消息正在处理，请稍候。',
  DUPLICATE_REQUEST: '这条消息已经提交过，请查看会话历史。',
  RISK_HANDOFF_REQUIRED: '该问题需要人工客服处理，已为你转接。',
  TOOL_BUDGET_EXCEEDED: '操作过于频繁，请稍后重试或转人工。',
  RATE_LIMITED: '操作过于频繁，请稍后重试。',
  UPSTREAM_UNAVAILABLE: '服务暂时不可用，请稍后重试或转人工。',
  INTERNAL_ERROR: '服务暂时不可用，请稍后重试。',
  NETWORK_ERROR: '网络连接失败，请检查网络后重试。',
  STREAM_ABORTED: '连接已中断，请重试或查看会话历史。',
  UNKNOWN: '请求失败，请稍后重试。',
}

/** HTTP 状态兜底文案（用于非信封响应）。 */
const STATUS_MESSAGES: Record<number, string> = {
  400: '请求参数不合法，请检查后重试。',
  401: '登录状态已失效，请重新登录。',
  403: '当前账号没有执行该操作的权限。',
  404: '未找到请求的资源。',
  405: '当前服务不支持该操作。',
  409: '请求冲突，请刷新后重试。',
  413: '文件过大，请压缩后重试。',
  415: '文件类型不受支持。',
  429: '操作过于频繁，请稍后重试。',
  500: '服务暂时不可用，请稍后重试。',
  502: '服务暂时不可用，请稍后重试。',
  503: '服务暂时不可用，请稍后重试或转人工。',
}

export function messageForCode(code: string): string {
  return CODE_MESSAGES[code] ?? CODE_MESSAGES.UNKNOWN
}

export function messageForStatus(status: number): string {
  return STATUS_MESSAGES[status] ?? CODE_MESSAGES.UNKNOWN
}

/** 从统一错误信封构造 ApiError。 */
export function apiErrorFromEnvelope(
  status: number,
  body: ErrorBody,
  requestId: string | null,
): ApiError {
  return new ApiError({
    code: body.code,
    message: body.message || messageForCode(body.code),
    status,
    retryable: body.retryable,
    retryAfterMs: body.retry_after_ms,
    details: body.details,
    requestId,
  })
}

/** 非信封响应（如 FastAPI 默认 404/405）的兜底映射。 */
export function apiErrorFromRaw(status: number, raw: unknown): ApiError {
  let detail: string | null = null
  if (raw && typeof raw === 'object' && 'detail' in raw) {
    const value = (raw as { detail?: unknown }).detail
    if (typeof value === 'string') detail = value
  }
  const code =
    status === 404 ? 'NOT_FOUND' : status === 405 ? 'METHOD_NOT_ALLOWED' : `HTTP_${status}`
  return new ApiError({
    code,
    message: messageForStatus(status),
    status,
    retryable: status >= 500,
    details: detail ? { detail } : {},
  })
}

/** 网络层失败（fetch 抛错 / 连接中断）。 */
export function networkError(cause?: unknown): ApiError {
  return new ApiError({
    code: 'NETWORK_ERROR',
    message: messageForCode('NETWORK_ERROR'),
    status: 0,
    retryable: true,
    details: cause instanceof Error ? { cause: cause.name } : {},
  })
}

/** 判断未知异常是否为 ApiError，否则包装为内部错误。 */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError({
      code: 'STREAM_ABORTED',
      message: messageForCode('STREAM_ABORTED'),
      status: 0,
      retryable: true,
    })
  }
  return new ApiError({
    code: 'INTERNAL_ERROR',
    message: messageForCode('INTERNAL_ERROR'),
    status: 0,
    retryable: true,
    details: error instanceof Error ? { cause: error.name } : {},
  })
}

export { CODE_MESSAGES }
