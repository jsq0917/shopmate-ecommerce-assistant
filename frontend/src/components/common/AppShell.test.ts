import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

import AppShell from '@/components/common/AppShell.vue'
import { useAuthStore } from '@/stores/auth'

/**
 * 账号隔离的缓存层回归：AppShell 用 keep-alive 缓存对话页，如果缓存键不含账号，
 * 换账号后会复用上一个账号的 ChatView 实例（onMounted 不再执行），对话列表不刷新。
 * 这里用「实例被 setup 了几次」直接观测是否重建。
 */

const mounted: string[] = []

const ChatStub = defineComponent({
  // 名字必须和 AppShell 里 keep-alive 的 include="ChatView" 对上
  name: 'ChatView',
  setup() {
    mounted.push('chat')
    return () => h('div', 'chat-view')
  },
})

const LoginStub = defineComponent({
  name: 'LoginView',
  setup: () => () => h('div', 'login-view'),
})

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'chat', component: ChatStub },
      { path: '/login', name: 'login', component: LoginStub },
    ],
  })
}

describe('AppShell 账号隔离', () => {
  it('切换账号后对话页实例重建，不复用上一个账号的缓存', async () => {
    mounted.length = 0
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = {
      user_id: 'user-a',
      email: 'a@example.invalid',
      display_name_masked: 'a***',
      role: 'shopper',
      shop_id: 'shop-1',
      is_synthetic: true,
    }

    const router = buildRouter()
    await router.push('/')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(mounted).toHaveLength(1)
    expect(wrapper.text()).toContain('chat-view')

    // 离开对话页：实例留在 keep-alive 缓存里，不会重新 setup。
    await router.push('/login')
    await flushPromises()
    expect(mounted).toHaveLength(1)

    // 换成另一个账号再回到对话页：必须是新实例（旧实例被淘汰）。
    auth.user = { ...auth.user!, user_id: 'user-b', email: 'b@example.invalid' }
    await router.push('/')
    await flushPromises()
    expect(mounted).toHaveLength(2)
  })

  it('同一账号在页面间来回切换仍复用缓存（不因隔离而丢状态）', async () => {
    mounted.length = 0
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = {
      user_id: 'user-a',
      email: 'a@example.invalid',
      display_name_masked: 'a***',
      role: 'shopper',
      shop_id: 'shop-1',
      is_synthetic: true,
    }

    const router = buildRouter()
    await router.push('/')
    await router.isReady()
    mount(AppShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    await router.push('/login')
    await flushPromises()
    await router.push('/')
    await flushPromises()

    expect(mounted).toHaveLength(1)
  })
})
