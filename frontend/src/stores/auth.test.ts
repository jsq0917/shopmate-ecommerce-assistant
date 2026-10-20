import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { getAccessToken, setAccessToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { MeData, TokenData } from '@/api/types'

vi.mock('@/api/endpoints', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    refresh: vi.fn(),
    logout: vi.fn(),
  },
}))

const { authApi } = await import('@/api/endpoints')

const tokenData: TokenData = {
  access_token: 'access-token-1',
  token_type: 'bearer',
  expires_in: 900,
  refresh_token: null,
  user: {
    user_id: 'u-1',
    email: 'shopper@example.com',
    display_name_masked: '张*',
    role: 'shopper',
    shop_id: null,
    is_synthetic: false,
  },
} as unknown as TokenData

const meData: MeData = {
  user_id: 'u-1',
  email: 'shopper@example.com',
  display_name_masked: '张*',
  role: 'shopper',
  shop_id: null,
  permissions: ['chat:write', 'orders:read'],
} as unknown as MeData

function setCsrfCookie(value: string): void {
  document.cookie = `shopmate_csrf=${encodeURIComponent(value)}`
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setAccessToken(null)
    document.cookie = 'shopmate_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
    vi.clearAllMocks()
  })

  it('登录成功后写入内存 token 并加载权限', async () => {
    vi.mocked(authApi.login).mockResolvedValue(tokenData)
    vi.mocked(authApi.me).mockResolvedValue(meData)

    const store = useAuthStore()
    const user = await store.login('shopper@example.com', 'pw', 'cap-token', '42')

    expect(getAccessToken()).toBe('access-token-1')
    expect(user.email).toBe('shopper@example.com')
    expect(store.permissions).toEqual(['chat:write', 'orders:read'])
    expect(store.isAuthenticated).toBe(true)
    expect(store.role).toBe('shopper')
  })

  it('登录失败保持未认证', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('bad credentials'))

    const store = useAuthStore()
    await expect(store.login('a@b.c', 'pw', 't', '1')).rejects.toThrow('bad credentials')
    expect(getAccessToken()).toBeNull()
    expect(store.user).toBeNull()
  })

  it('refreshSession 读取 CSRF cookie 并拼接头', async () => {
    setCsrfCookie('csrf-token-1')
    vi.mocked(authApi.refresh).mockResolvedValue(tokenData)

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(true)
    expect(authApi.refresh).toHaveBeenCalledWith('csrf-token-1')
    expect(getAccessToken()).toBe('access-token-1')
  })

  it('缺少 CSRF cookie 时刷新失败并清空会话', async () => {
    const store = useAuthStore()
    setAccessToken('stale-token')

    const ok = await store.refreshSession()

    expect(ok).toBe(false)
    expect(authApi.refresh).not.toHaveBeenCalled()
    expect(getAccessToken()).toBeNull()
    expect(store.user).toBeNull()
  })

  it('refresh 接口失败时清空会话', async () => {
    setCsrfCookie('csrf-token-1')
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('expired'))

    const store = useAuthStore()
    const ok = await store.refreshSession()

    expect(ok).toBe(false)
    expect(getAccessToken()).toBeNull()
  })

  it('并发 refreshOnce 只发一次刷新请求', async () => {
    setCsrfCookie('csrf-token-1')
    vi.mocked(authApi.refresh).mockResolvedValue(tokenData)

    const store = useAuthStore()
    const results = await Promise.all([store.refreshOnce(), store.refreshOnce(), store.refreshOnce()])

    expect(results).toEqual([true, true, true])
    expect(authApi.refresh).toHaveBeenCalledTimes(1)
  })

  it('bootstrap：无 token 时走静默刷新', async () => {
    setCsrfCookie('csrf-token-1')
    vi.mocked(authApi.refresh).mockResolvedValue(tokenData)

    const store = useAuthStore()
    await store.bootstrap()

    expect(authApi.refresh).toHaveBeenCalledTimes(1)
    expect(store.bootstrapped).toBe(true)
  })

  it('bootstrap：已有 token 时加载 me', async () => {
    setAccessToken('token-1')
    vi.mocked(authApi.me).mockResolvedValue(meData)

    const store = useAuthStore()
    await store.bootstrap()

    expect(authApi.me).toHaveBeenCalledTimes(1)
    expect(authApi.refresh).not.toHaveBeenCalled()
    expect(store.permissions).toHaveLength(2)
  })

  it('bootstrap 重复调用只执行一次', async () => {
    setAccessToken('token-1')
    vi.mocked(authApi.me).mockResolvedValue(meData)

    const store = useAuthStore()
    await store.bootstrap()
    await store.bootstrap()

    expect(authApi.me).toHaveBeenCalledTimes(1)
  })

  it('isAuthenticated 对 token 变化保持响应（P0-1 回归护栏）', async () => {
    vi.mocked(authApi.login).mockResolvedValue(tokenData)
    vi.mocked(authApi.me).mockResolvedValue(meData)

    const store = useAuthStore()

    // 关键：在写入 token 之前先求值一次（模拟路由守卫在初始 /login 页的首次求值）。
    // 若 isAuthenticated 依赖的是非响应式数据，这次 false 会被永久缓存，
    // 登录成功后守卫仍判未认证，用户被踢回登录页。
    expect(store.isAuthenticated).toBe(false)

    await store.login('shopper@example.com', 'pw', 'cap-token', '42')
    expect(store.isAuthenticated).toBe(true)

    store.clearSession()
    expect(store.isAuthenticated).toBe(false)
    expect(getAccessToken()).toBeNull()
  })

  it('logout 失败也清理本地会话', async () => {
    vi.mocked(authApi.logout).mockRejectedValue(new Error('offline'))
    const store = useAuthStore()
    setAccessToken('token-1')

    await store.logout()

    expect(getAccessToken()).toBeNull()
    expect(store.user).toBeNull()
  })
})
