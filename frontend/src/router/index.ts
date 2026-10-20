/**
 * 路由。角色分流只是体验层：所有数据接口仍由后端做权限校验，
 * 前端隐藏入口不构成任何安全边界（AGENTS.md 13.4 / 业务铁律 4）。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    auth?: boolean
    roles?: Array<'shopper' | 'support' | 'admin'>
    title?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录 / 注册' },
  },
  {
    path: '/',
    name: 'chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { auth: true, title: '智能客服' },
  },
  {
    path: '/products',
    name: 'products',
    component: () => import('@/views/ProductsView.vue'),
    meta: { auth: true, title: '商品中心' },
  },
  {
    path: '/orders',
    name: 'orders',
    component: () => import('@/views/OrdersView.vue'),
    meta: { auth: true, title: '我的订单' },
  },
  {
    path: '/orders/:orderId',
    name: 'order-detail',
    component: () => import('@/views/OrderDetailView.vue'),
    meta: { auth: true, title: '订单详情' },
  },
  {
    path: '/handoff',
    name: 'handoff',
    component: () => import('@/views/HandoffTicketsView.vue'),
    meta: { auth: true, title: '我的工单' },
  },
  {
    path: '/support',
    name: 'support-tickets',
    component: () => import('@/views/SupportTicketsView.vue'),
    meta: { auth: true, roles: ['support', 'admin'], title: '客服工作台' },
  },
  {
    path: '/support/tickets/:ticketId',
    name: 'support-ticket-detail',
    component: () => import('@/views/SupportTicketDetailView.vue'),
    meta: { auth: true, roles: ['support', 'admin'], title: '工单详情' },
  },
  {
    path: '/admin',
    name: 'admin-knowledge',
    component: () => import('@/views/AdminKnowledgeView.vue'),
    meta: { auth: true, roles: ['admin'], title: '知识库管理' },
  },
  {
    path: '/admin/chunks',
    name: 'admin-chunks',
    component: () => import('@/views/AdminChunksView.vue'),
    meta: { auth: true, roles: ['admin'], title: '知识单元管理' },
  },
  {
    path: '/admin/eval',
    name: 'admin-eval',
    component: () => import('@/views/AdminEvalView.vue'),
    meta: { auth: true, roles: ['admin'], title: '评测与模型' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  if (to.meta.auth && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.roles && auth.role && !to.meta.roles.includes(auth.role as never)) {
    return { path: '/', query: { forbidden: '1' } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} · ShopMate` : 'ShopMate 电商智能客服'
})

export default router
