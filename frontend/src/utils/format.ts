/**
 * 展示格式化工具。所有价格/库存/政策事实均来自 API，本模块只做格式化与标签映射，
 * 不包含任何业务常量（禁止硬编码价格、库存或政策）。
 */

const CNY = '¥'

/** 整数分 -> 货币字符串。非法输入返回 '--'，不猜测。 */
export function formatCents(cents: number | null | undefined, currency = 'CNY'): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return '--'
  const major = cents / 100
  try {
    return new Intl.NumberFormat('zh-CN', { style: 'currency', currency }).format(major)
  } catch {
    return `${CNY}${major.toFixed(2)}`
  }
}

/** 金额 + 币种（币种未知时单独标注）。 */
export function formatMoney(cents: number | null | undefined, currency?: string | null): string {
  const symbol = currency && currency !== 'CNY' ? ` ${currency}` : ''
  return `${formatCents(cents, currency || 'CNY')}${symbol}`
}

/** ISO UTC -> 本地时间 'YYYY-MM-DD HH:mm'。 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '--'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

/** ISO UTC -> 本地日期 'YYYY-MM-DD'。 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '--'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 等待秒数 -> 'x 秒 / x 分钟 / x 小时'。 */
export function formatWaiting(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '--'
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`
  return `${Math.floor(seconds / 3600)} 小时`
}

const STOCK_LABELS: Record<string, string> = {
  in_stock: '有货',
  out_of_stock: '缺货',
  unknown: '库存未知',
}

export function stockStatusLabel(status: string | null | undefined): string {
  if (!status) return '库存未知'
  return STOCK_LABELS[status] ?? status
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  created: '已下单',
  paid: '已付款',
  processing: '处理中',
  shipped: '已发货',
  delivered: '已送达',
  completed: '已完成',
  cancelled: '已取消',
}

export function orderStatusLabel(status: string | null | undefined): string {
  if (!status) return '--'
  return ORDER_STATUS_LABELS[status] ?? status
}

const SHIPMENT_STATUS_LABELS: Record<string, string> = {
  pending: '待揽收',
  picked_up: '已揽收',
  in_transit: '运输中',
  out_for_delivery: '派送中',
  delivered: '已送达',
  exception: '异常',
}

export function shipmentStatusLabel(status: string | null | undefined): string {
  if (!status) return '--'
  return SHIPMENT_STATUS_LABELS[status] ?? status
}

const TICKET_STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  assigned: '已接管',
  resolved: '已解决',
  closed: '已关闭',
}

export function ticketStatusLabel(status: string | null | undefined): string {
  if (!status) return '--'
  return TICKET_STATUS_LABELS[status] ?? status
}

const RISK_LABELS: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '紧急',
}

export function riskLevelLabel(level: string | null | undefined): string {
  if (!level) return '--'
  return RISK_LABELS[level] ?? level
}

const ROUTE_LABELS: Record<string, string> = {
  product_discovery: '商品咨询',
  product_compare: '商品比较',
  product_fact: '商品详情',
  policy_faq: '政策问答',
  order_status: '订单查询',
  shipment: '物流查询',
  return_eligibility: '退货资格',
  return_request: '退货申请',
  complaint_handoff: '投诉转人工',
  smalltalk_or_unknown: '其他',
}

export function routeLabel(route: string | null | undefined): string {
  if (!route) return '--'
  return ROUTE_LABELS[route] ?? route
}

const DECISION_LABELS: Record<string, string> = {
  eligible: '符合退货条件',
  ineligible: '不符合退货条件',
  needs_clarification: '需要补充信息',
  needs_manual_review: '需要人工审核',
}

export function decisionLabel(decision: string | null | undefined): string {
  if (!decision) return '--'
  return DECISION_LABELS[decision] ?? decision
}

const RETURN_REASON_LABELS: Record<string, string> = {
  SIZE_OR_FIT: '尺寸或规格不符',
  NO_LONGER_NEEDED: '不再需要',
  DAMAGED_ON_ARRIVAL: '到货损坏',
  WRONG_ITEM: '发错商品',
  QUALITY_ISSUE: '质量问题',
  OTHER: '其他',
}

export function returnReasonLabel(code: string | null | undefined): string {
  if (!code) return '--'
  return RETURN_REASON_LABELS[code] ?? code
}

export const RETURN_REASON_OPTIONS = Object.entries(RETURN_REASON_LABELS).map(
  ([value, label]) => ({ value, label }),
)

const HANDOFF_REASON_LABELS: Record<string, string> = {
  USER_REQUESTS_HUMAN: '用户要求人工',
  COMPLAINT: '投诉',
  LEGAL_OR_REGULATORY: '法律或监管',
  PERSONAL_SAFETY: '人身安全',
  PRIVACY_OR_ACCOUNT_TAKEOVER: '隐私或账号安全',
  MONEY_DECISION_REQUIRED: '资金决策',
  HIGH_VALUE_ORDER: '高额订单',
  RETURN_REASON_REQUIRES_REVIEW: '退货原因需审核',
  POLICY_CONFLICT: '政策冲突',
  INSUFFICIENT_EVIDENCE_RIGHTS: '证据不足',
  TOOL_FAILURE_REPEATED: '工具连续失败',
  TOOL_MODEL_CONFLICT: '工具与模型冲突',
  OUTPUT_GUARD_MONEY: '输出护栏：资金承诺',
  OUTPUT_GUARD_PII: '输出护栏：隐私',
  ABNORMAL_ORDER_PATTERN: '订单模式异常',
}

export function handoffReasonLabel(code: string | null | undefined): string {
  if (!code) return '--'
  return HANDOFF_REASON_LABELS[code] ?? code
}

export const HANDOFF_REASON_OPTIONS: { value: string; label: string }[] = [
  'USER_REQUESTS_HUMAN',
  'COMPLAINT',
  'LEGAL_OR_REGULATORY',
  'MONEY_DECISION_REQUIRED',
  'POLICY_CONFLICT',
].map((value) => ({ value, label: HANDOFF_REASON_LABELS[value] }))

const DOC_TYPE_LABELS: Record<string, string> = {
  policy: '政策',
  faq: '常见问题',
  manual: '说明书',
  warranty: '保修',
  invoice: '发票',
  shipping: '配送',
  other: '其他',
}

export function docTypeLabel(type: string | null | undefined): string {
  if (!type) return '--'
  return DOC_TYPE_LABELS[type] ?? type
}

const PARSE_STATUS_LABELS: Record<string, string> = {
  pending: '待解析',
  ready: '就绪',
  failed: '解析失败',
}

export function parseStatusLabel(status: string | null | undefined): string {
  if (!status) return '--'
  return PARSE_STATUS_LABELS[status] ?? status
}

const QUALITY_LABELS: Record<string, string> = {
  correct: '正确',
  incorrect: '错误',
  needs_knowledge: '需补充知识',
}

export function qualityLabel(code: string | null | undefined): string {
  if (!code) return '--'
  return QUALITY_LABELS[code] ?? code
}

/** 未知属性值：绝不编造。 */
export function attributeValueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '暂无数据'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

/** 生成客户端消息 ID（聊天幂等）。 */
export function newUuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const random = (Math.random() * 16) | 0
    return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16)
  })
}
