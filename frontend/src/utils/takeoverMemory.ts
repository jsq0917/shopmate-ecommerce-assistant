/**
 * 「我在本机成功接管过哪些工单」的会话级备忘。
 *
 * 为什么需要这一层：
 * `assigned_to_me` 是后端按 `assigned_to == 当前 user_id` 派生的字段（阶段 21 新增）。
 * 滚动发布 / 镜像未重建时，旧实例不返回该字段，前端读到的就是 `undefined`。若直接按
 * falsy 处理，会把「自己刚接管的工单」误判成「别人接管的」，表现为接管按钮不消失、
 * 回复框永久禁用——功能看起来像坏了，其实是前后端版本错位。
 *
 * 语义约束（只在字段缺失时使用）：
 * - 只有「本人点击接管且后端返回成功」才写入。后端 `assign` 在未指定 `assignee_user_id`
 *   时把处理人设为调用者，所以这条记录与后端事实一致。
 * - 按 `user_id` 分桶，绝不跨账号继承：否则换账号后会看到上一个账号的接管记录，
 *   与阶段 21 修掉的账号数据隔离问题同源。
 * - 只存 ticket_id，不含任何会话内容或 PII；存在 sessionStorage，关闭标签页即失效。
 */

const STORAGE_PREFIX = 'shopmate.taken-over.v1'

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null
    return window.sessionStorage
  } catch {
    // 隐私模式下 sessionStorage 可能直接抛错，降级为「没有备忘」而不是整页崩掉。
    return null
  }
}

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}.${userId}`
}

function read(userId: string | null | undefined): string[] {
  if (!userId) return []
  const store = storage()
  if (!store) return []
  try {
    const raw = store.getItem(storageKey(userId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function write(userId: string, ticketIds: string[]): void {
  const store = storage()
  if (!store) return
  try {
    if (!ticketIds.length) {
      store.removeItem(storageKey(userId))
      return
    }
    store.setItem(storageKey(userId), JSON.stringify(ticketIds))
  } catch {
    // 配额满 / 被禁用：备忘失效不影响主流程，后端字段恢复后自然正确。
  }
}

/** 记录一条「我接管成功了」。`userId` 为空时直接放弃，避免写入无法归属的记录。 */
export function rememberTakeover(userId: string | null | undefined, ticketId: string): void {
  if (!userId || !ticketId) return
  const current = read(userId)
  if (current.includes(ticketId)) return
  write(userId, [...current, ticketId])
}

export function forgetTakeover(userId: string | null | undefined, ticketId: string): void {
  if (!userId || !ticketId) return
  const current = read(userId)
  if (!current.includes(ticketId)) return
  write(userId, current.filter((item) => item !== ticketId))
}

/**
 * 按后端权威值校准备忘：`true` 补齐、`false` 清除。
 *
 * 这样一旦新版本后端上线，残留的本地记录会被自动纠正，不会长期盖住服务端事实。
 */
export function syncTakeoverMemory(
  userId: string | null | undefined,
  ticketId: string,
  assignedToMe: boolean,
): void {
  if (assignedToMe) {
    rememberTakeover(userId, ticketId)
    return
  }
  forgetTakeover(userId, ticketId)
}

/** 只在后端未返回 `assigned_to_me` 时作为兜底；有权威值时应优先用权威值。 */
export function hasTakeoverMemory(userId: string | null | undefined, ticketId: string): boolean {
  return read(userId).includes(ticketId)
}
