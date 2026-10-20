/**
 * 认证状态。
 *
 * 安全约束（docs/06-api.md 第 2 节）：
 * - access token 只保存在内存（Pinia state），不写 localStorage / URL / 日志；
 * - 刷新依赖 HttpOnly refresh cookie + 可读的 CSRF cookie（仅用于拼 X-CSRF-Token 头）；
 * - 页面刷新后先尝试静默刷新，失败则回到登录页；
 * - 前端角色菜单只是体验优化，真正的权限校验在后端。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getAccessToken, setAccessToken, setUnauthorizedHandler } from '@/api/client'
import { authApi } from '@/api/endpoints'
import type { MeData, TokenData, UserSummary } from '@/api/types'

const CSRF_COOKIE_NAME = 'shopmate_csrf'

function readCsrfToken(): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${CSRF_COOKIE_NAME}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return null
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserSummary | null>(null)
  const permissions = ref<string[]>([])
  const bootstrapped = ref(false)
  let refreshInFlight: Promise<boolean> | null = null

  const isAuthenticated = computed(() => getAccessToken() !== null)
  const role = computed(() => user.value?.role ?? null)

  function applyToken(token: TokenData): void {
    setAccessToken(token.access_token)
    user.value = token.user
    permissions.value = []
  }

  async function login(email: string, password: string, captchaToken: string, captchaAnswer: string) {
    const token = await authApi.login({ email, password, captcha_token: captchaToken, captcha_answer: captchaAnswer })
    applyToken(token)
    await loadMe()
    return token.user
  }

  async function loadMe(): Promise<MeData> {
    const me = await authApi.me()
    user.value = {
      user_id: me.user_id,
      email: me.email,
      display_name_masked: me.display_name_masked,
      role: me.role,
      shop_id: me.shop_id,
      is_synthetic: true,
    }
    permissions.value = me.permissions
    return me
  }

  async function refreshSession(): Promise<boolean> {
    const csrf = readCsrfToken()
    if (!csrf) {
      clearSession()
      return false
    }
    try {
      const token = await authApi.refresh(csrf)
      applyToken(token)
      return true
    } catch {
      clearSession()
      return false
    }
  }

  /** 串行化刷新：并发 401 只发一次 /auth/refresh。 */
  function refreshOnce(): Promise<boolean> {
    if (!refreshInFlight) {
      refreshInFlight = refreshSession().finally(() => {
        refreshInFlight = null
      })
    }
    return refreshInFlight
  }

  function clearSession(): void {
    setAccessToken(null)
    user.value = null
    permissions.value = []
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // 登出失败也清理本地会话；服务端 cookie 会随过期自然失效。
    }
    clearSession()
  }

  async function bootstrap(): Promise<void> {
    if (bootstrapped.value) return
    bootstrapped.value = true
    if (!getAccessToken()) {
      await refreshOnce()
    } else {
      try {
        await loadMe()
      } catch {
        clearSession()
      }
    }
  }

  setUnauthorizedHandler(() => refreshOnce())

  return {
    user,
    permissions,
    bootstrapped,
    isAuthenticated,
    role,
    login,
    loadMe,
    refreshSession,
    refreshOnce,
    clearSession,
    logout,
    bootstrap,
  }
})
