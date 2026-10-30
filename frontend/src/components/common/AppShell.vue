<script setup lang="ts">
/**
 * 应用外壳：顶部导航 + 合成数据横幅 + 购物车入口 + 用户信息 + 移动端抽屉。
 * 导航按角色展示仅为体验层，权限校验以后端为准。
 */

import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElDrawer, ElMessageBox } from 'element-plus'

import { useCart } from '@/composables/useCart'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()
const cart = useCart()

const drawerVisible = ref(false)
const forbidden = ref(false)

watch(
  () => route.query.forbidden,
  (value) => {
    forbidden.value = value === '1'
  },
  { immediate: true },
)

const roleLabel = computed(() => {
  if (auth.role === 'support') return '客服'
  if (auth.role === 'admin') return '管理员'
  if (auth.role === 'shopper') return '消费者'
  return '--'
})

const navItems = computed(() => {
  const items = [
    { path: '/', label: '智能客服' },
    { path: '/products', label: '商品中心' },
    { path: '/orders', label: '我的订单' },
    { path: '/handoff', label: '我的工单' },
  ]
  if (auth.role === 'support' || auth.role === 'admin') {
    items.push({ path: '/support', label: '客服工作台' })
  }
  if (auth.role === 'admin') {
    items.push({ path: '/admin', label: '管理后台' })
  }
  return items
})

const isAuthPage = computed(() => route.name === 'login')

/** keep-alive 的缓存键：只有同一账号才复用同一个页面实例。 */
const accountKey = computed(() => auth.user?.user_id ?? 'anonymous')

const displayName = computed(() => auth.user?.display_name_masked ?? auth.user?.email ?? '未登录')
const avatarText = computed(() => displayName.value.trim().slice(0, 1) || 'S')

async function onLogout(): Promise<void> {
  try {
    await ElMessageBox.confirm('确认退出当前登录账号？', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await auth.logout()
  // 购物车是浏览器级本地状态（localStorage），登出后必须清空，否则下一个登录的账号
  // 会看到上一个人加购的商品。
  cart.clear()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="sm-shell">
    <header v-if="!isAuthPage" class="sm-shell-header">
      <button class="sm-menu-button" type="button" aria-label="打开导航菜单" @click="drawerVisible = true">
        ☰
      </button>
      <router-link class="sm-brand" to="/">
        <span class="sm-brand-mark">SM</span>
        <span class="sm-brand-text">
          <strong>ShopMate</strong>
          <small>智能导购与客服</small>
        </span>
      </router-link>

      <nav class="sm-nav" aria-label="主导航">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="sm-nav-link"
          active-class="sm-nav-link-active"
        >
          {{ item.label }}
        </router-link>
      </nav>

      <div class="sm-shell-user">
        <router-link to="/checkout" class="sm-cart" aria-label="购物车">
          <span class="sm-cart-icon">🛒</span>
          <span v-if="cart.count.value" class="sm-cart-badge">{{ cart.count.value }}</span>
        </router-link>
        <div class="sm-user">
          <span class="sm-avatar">{{ avatarText }}</span>
          <span class="sm-user-meta">
            <strong>{{ displayName }}</strong>
            <small>{{ roleLabel }}</small>
          </span>
        </div>
        <ElButton size="small" text @click="onLogout">退出</ElButton>
      </div>
    </header>

    <ElAlert
      v-if="!isAuthPage && system.meta?.is_synthetic"
      class="sm-synthetic-banner"
      type="warning"
      :closable="false"
      show-icon
    >
      <strong>合成演示数据</strong>
      <span class="sm-synthetic-text">{{ system.meta.notice }}</span>
    </ElAlert>

    <ElAlert
      v-if="!isAuthPage && forbidden"
      class="sm-synthetic-banner"
      type="error"
      :closable="false"
      show-icon
      title="无权访问该页面"
    >
      当前账号没有该页面的访问权限（{{ roleLabel }}）。如需访问，请联系管理员。
    </ElAlert>

    <main class="sm-shell-main">
      <router-view v-slot="{ Component }">
        <!--
          账号隔离：keep-alive 只按组件名缓存，同一个 SPA 会话里换账号会复用上一个账号的
          ChatView 实例（onMounted 不再执行），会话列表与消息就停留在旧账号上。
          把当前 user_id 拼进缓存键，换人即换实例；max=1 保证旧实例被淘汰释放。
        -->
        <keep-alive include="ChatView" :max="1">
          <component :is="Component" :key="accountKey" />
        </keep-alive>
      </router-view>
    </main>

    <ElDrawer v-model="drawerVisible" title="导航" direction="ltr" size="70%">
      <nav class="sm-drawer-nav" aria-label="移动端导航">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="sm-drawer-link"
          @click="drawerVisible = false"
        >
          {{ item.label }}
        </router-link>
        <router-link to="/checkout" class="sm-drawer-link" @click="drawerVisible = false">
          购物车<span v-if="cart.count.value" class="sm-drawer-badge">{{ cart.count.value }}</span>
        </router-link>
      </nav>
      <div class="sm-drawer-user">
        <p class="sm-muted">当前账号：{{ displayName }}（{{ roleLabel }}）</p>
        <p class="sm-muted">数据分类：{{ system.meta?.data_classification ?? '--' }}</p>
      </div>
    </ElDrawer>
  </div>
</template>

<style scoped>
.sm-shell {
  height: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.sm-shell-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 22px;
  background: rgb(255 255 255 / 88%);
  backdrop-filter: saturate(180%) blur(14px);
  border-bottom: 1px solid var(--sm-border);
}

.sm-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--sm-text);
  flex: none;
}

.sm-brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: var(--sm-gradient);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.4px;
  box-shadow: 0 6px 16px rgb(59 91 253 / 30%);
}

.sm-brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.sm-brand-text strong {
  font-size: 15px;
  letter-spacing: -0.01em;
}

.sm-brand-text small {
  font-size: 10px;
  color: var(--sm-text-tertiary);
  letter-spacing: 0.06em;
}

.sm-nav {
  display: flex;
  gap: 4px;
  margin-left: 4px;
  overflow-x: auto;
  scrollbar-width: none;
}

.sm-nav::-webkit-scrollbar {
  display: none;
}

.sm-nav-link {
  padding: 7px 13px;
  border-radius: var(--sm-radius-pill);
  color: var(--sm-text-secondary);
  font-size: 13px;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.sm-nav-link:hover {
  background: var(--sm-bg);
  color: var(--sm-text);
}

.sm-nav-link-active {
  background: var(--sm-primary-soft);
  color: var(--sm-primary-dark);
  font-weight: 600;
}

.sm-shell-user {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}

.sm-cart {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: var(--sm-bg);
  border: 1px solid var(--sm-border);
  transition: background 0.15s ease, transform 0.15s ease;
}

.sm-cart:hover {
  background: var(--sm-primary-soft);
  transform: translateY(-1px);
}

.sm-cart-icon {
  font-size: 16px;
}

.sm-cart-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--sm-accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: grid;
  place-items: center;
  border: 2px solid #fff;
}

.sm-user {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sm-avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #dbe2ff, #eef1ff);
  color: var(--sm-primary-dark);
  font-weight: 700;
  font-size: 13px;
}

.sm-user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.sm-user-meta strong {
  font-size: 12px;
  font-weight: 600;
}

.sm-user-meta small {
  font-size: 11px;
  color: var(--sm-text-tertiary);
}

.sm-synthetic-banner {
  margin: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
}

.sm-synthetic-text {
  margin-left: 8px;
}

.sm-shell-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.sm-menu-button {
  display: none;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
  border-radius: 9px;
  padding: 4px 10px;
  font-size: 16px;
  cursor: pointer;
}

.sm-drawer-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sm-drawer-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 12px;
  border-radius: 10px;
  color: var(--sm-text);
}

.sm-drawer-link:hover,
.sm-drawer-link.router-link-active {
  background: var(--sm-primary-soft);
  color: var(--sm-primary-dark);
}

.sm-drawer-badge {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-accent);
  color: #fff;
  font-size: 11px;
}

.sm-drawer-user {
  margin-top: 16px;
  border-top: 1px solid var(--sm-border);
  padding-top: 12px;
}

@media (max-width: 900px) {
  .sm-brand-text,
  .sm-user-meta {
    display: none;
  }
}

@media (max-width: 768px) {
  .sm-shell-header {
    gap: 10px;
    padding: 8px 12px;
  }

  .sm-menu-button {
    display: block;
  }

  .sm-nav {
    display: none;
  }
}
</style>
