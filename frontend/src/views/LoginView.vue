<script setup lang="ts">
/**
 * 登录 / 注册。验证码由 GET /auth/captcha 提供（算式题，答案在服务端签名，
 * 前端不存储明文）。access token 只进内存，刷新依赖 HttpOnly cookie。
 *
 * 演示账号按钮只填充「合成演示口令」，验证码仍需手动输入（服务端校验，不可绕过）。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElForm, ElFormItem, ElInput, ElTabPane, ElTabs } from 'element-plus'

import { authApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

/** 演示口令：仅用于合成数据店铺，公开且不可用于任何真实环境。 */
const DEMO_PASSWORD = 'ShopMate-Demo-Only-2026'

const DEMO_ACCOUNTS = [
  { role: '消费者', email: 'shopper01@example.invalid', hint: '下单 / 退款 / 转人工' },
  { role: '客服', email: 'support01@example.invalid', hint: '工单处理 / 退款审核' },
  { role: '管理员', email: 'admin01@example.invalid', hint: '知识库与评测' },
]

const activeTab = ref<'login' | 'register'>('login')
const captchaToken = ref('')
const captchaQuestion = ref('')
const loading = ref(false)
const error = ref<ApiError | null>(null)
const notice = ref('')

const loginForm = reactive({ email: '', password: '', captchaAnswer: '' })
const registerForm = reactive({ email: '', password: '', captchaAnswer: '' })

const canSubmitLogin = computed(
  () => loginForm.email.trim() !== '' && loginForm.password !== '' && loginForm.captchaAnswer.trim() !== '',
)
const canSubmitRegister = computed(
  () =>
    registerForm.email.trim() !== '' &&
    registerForm.password.length >= 8 &&
    registerForm.captchaAnswer.trim() !== '',
)

async function loadCaptcha(): Promise<void> {
  error.value = null
  try {
    const data = await authApi.captcha()
    captchaToken.value = data.captcha_token
    captchaQuestion.value = data.question
    loginForm.captchaAnswer = ''
    registerForm.captchaAnswer = ''
  } catch (caught) {
    error.value = toApiError(caught)
  }
}

function fillDemo(email: string): void {
  activeTab.value = 'login'
  loginForm.email = email
  loginForm.password = DEMO_PASSWORD
  notice.value = '已填入演示账号，请输入下方算式的结果后登录。'
}

async function onLogin(): Promise<void> {
  if (!canSubmitLogin.value || loading.value) return
  loading.value = true
  error.value = null
  try {
    await auth.login(
      loginForm.email.trim(),
      loginForm.password,
      captchaToken.value,
      loginForm.captchaAnswer.trim(),
    )
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.replace(next || '/')
  } catch (caught) {
    // loadCaptcha 会清空 error，因此先算好再刷新验证码，最后回填，保证用户可见。
    const apiError = toApiError(caught)
    await loadCaptcha()
    error.value = apiError
  } finally {
    loading.value = false
  }
}

async function onRegister(): Promise<void> {
  if (!canSubmitRegister.value || loading.value) return
  loading.value = true
  error.value = null
  notice.value = ''
  try {
    await authApi.register({
      email: registerForm.email.trim(),
      password: registerForm.password,
      captcha_token: captchaToken.value,
      captcha_answer: registerForm.captchaAnswer.trim(),
    })
    notice.value = '注册成功，请使用该邮箱登录。'
    loginForm.email = registerForm.email.trim()
    activeTab.value = 'login'
    await loadCaptcha()
  } catch (caught) {
    const apiError = toApiError(caught)
    await loadCaptcha()
    error.value = apiError
  } finally {
    loading.value = false
  }
}

onMounted(loadCaptcha)
</script>

<template>
  <div class="sm-login-page">
    <div class="sm-login-shell">
      <aside class="sm-login-aside">
        <div class="sm-login-brand">
          <span class="sm-login-mark">SM</span>
          <div>
            <strong>ShopMate</strong>
            <small>电商智能客服与轻导购</small>
          </div>
        </div>

        <h1 class="sm-login-headline">会查数据、<br />也会好好说话的客服</h1>
        <p class="sm-login-lead">
          商品推荐基于真实价格与库存，政策回答逐条附引用，售后问题一键转人工。
        </p>

        <ul class="sm-login-points">
          <li><span>🛍️</span>按预算和场景挑商品，价格库存实时</li>
          <li><span>📄</span>政策回答带文档、章节与生效日期</li>
          <li><span>📦</span>订单物流只看得到自己的数据</li>
          <li><span>🤝</span>投诉与异常自动升级人工</li>
        </ul>

        <p class="sm-login-note">演示环境使用合成数据，不接入真实支付与真实个人信息。</p>
      </aside>

      <section class="sm-login-card">
        <h2 class="sm-login-title">登录 ShopMate</h2>
        <p class="sm-muted">登录后可查询商品、政策、订单与售后进度。</p>

        <div class="sm-demo">
          <span class="sm-muted">演示账号</span>
          <div class="sm-demo-list">
            <button
              v-for="account in DEMO_ACCOUNTS"
              :key="account.email"
              type="button"
              class="sm-demo-chip"
              :title="account.email"
              @click="fillDemo(account.email)"
            >
              <strong>{{ account.role }}</strong>
              <small>{{ account.hint }}</small>
            </button>
          </div>
        </div>

        <ElAlert
          v-if="notice"
          class="sm-login-alert"
          type="success"
          :closable="false"
          show-icon
          :title="notice"
        />
        <ElAlert
          v-if="error"
          class="sm-login-alert"
          type="error"
          :closable="false"
          show-icon
          :title="error.message"
        />

        <ElTabs v-model="activeTab">
          <ElTabPane label="登录" name="login">
            <ElForm label-position="top" @submit.prevent="onLogin">
              <ElFormItem label="邮箱">
                <ElInput v-model="loginForm.email" type="email" autocomplete="username" placeholder="you@example.invalid" />
              </ElFormItem>
              <ElFormItem label="密码">
                <ElInput
                  v-model="loginForm.password"
                  type="password"
                  autocomplete="current-password"
                  placeholder="登录密码"
                  show-password
                  @keyup.enter="onLogin"
                />
              </ElFormItem>
              <ElFormItem label="验证码">
                <div class="sm-captcha-row">
                  <span class="sm-captcha-question">{{ captchaQuestion || '加载中…' }}</span>
                  <ElInput
                    v-model="loginForm.captchaAnswer"
                    class="sm-captcha-input"
                    placeholder="计算结果"
                    autocomplete="off"
                    @keyup.enter="onLogin"
                  />
                  <ElButton size="small" @click="loadCaptcha">换一题</ElButton>
                </div>
              </ElFormItem>
              <ElButton
                class="sm-login-submit"
                type="primary"
                size="large"
                :loading="loading"
                :disabled="!canSubmitLogin"
                @click="onLogin"
              >
                登录
              </ElButton>
            </ElForm>
          </ElTabPane>

          <ElTabPane label="注册" name="register">
            <ElForm label-position="top" @submit.prevent="onRegister">
              <ElFormItem label="邮箱">
                <ElInput v-model="registerForm.email" type="email" autocomplete="username" placeholder="you@example.invalid" />
              </ElFormItem>
              <ElFormItem label="密码（至少 8 位）">
                <ElInput
                  v-model="registerForm.password"
                  type="password"
                  autocomplete="new-password"
                  placeholder="至少 8 位字符"
                  show-password
                  @keyup.enter="onRegister"
                />
              </ElFormItem>
              <ElFormItem label="验证码">
                <div class="sm-captcha-row">
                  <span class="sm-captcha-question">{{ captchaQuestion || '加载中…' }}</span>
                  <ElInput
                    v-model="registerForm.captchaAnswer"
                    class="sm-captcha-input"
                    placeholder="计算结果"
                    autocomplete="off"
                    @keyup.enter="onRegister"
                  />
                  <ElButton size="small" @click="loadCaptcha">换一题</ElButton>
                </div>
              </ElFormItem>
              <ElButton
                class="sm-login-submit"
                type="primary"
                size="large"
                :loading="loading"
                :disabled="!canSubmitRegister"
                @click="onRegister"
              >
                注册
              </ElButton>
            </ElForm>
          </ElTabPane>
        </ElTabs>

        <p class="sm-muted sm-login-foot">
          客服与管理员账号由运营分配；消费者注册后默认进入消费者端。
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.sm-login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(900px 420px at 8% 0%, rgb(59 91 253 / 12%), transparent 70%),
    radial-gradient(760px 420px at 96% 10%, rgb(255 106 61 / 10%), transparent 70%),
    var(--sm-bg);
}

.sm-login-shell {
  width: min(960px, 100%);
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-radius: 24px;
  overflow: hidden;
  background: var(--sm-surface);
  border: 1px solid var(--sm-border);
  box-shadow: var(--sm-shadow-lg);
}

.sm-login-aside {
  padding: 36px 34px;
  background: var(--sm-gradient);
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sm-login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sm-login-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: rgb(255 255 255 / 18%);
  font-weight: 800;
  font-size: 13px;
}

.sm-login-brand strong {
  display: block;
  font-size: 16px;
}

.sm-login-brand small {
  font-size: 11px;
  opacity: 0.8;
}

.sm-login-headline {
  margin: 12px 0 0;
  font-size: 27px;
  line-height: 1.35;
  font-weight: 750;
  letter-spacing: -0.02em;
}

.sm-login-lead {
  margin: 0;
  font-size: 13px;
  opacity: 0.9;
  line-height: 1.7;
}

.sm-login-points {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
  opacity: 0.95;
}

.sm-login-points li {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sm-login-note {
  margin: auto 0 0;
  font-size: 11px;
  opacity: 0.72;
}

.sm-login-card {
  padding: 32px 30px;
}

.sm-login-title {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
}

.sm-login-alert {
  margin: 12px 0;
}

.sm-demo {
  margin: 16px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sm-demo-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.sm-demo-chip {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface-2);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.sm-demo-chip:hover {
  border-color: #c5ceff;
  background: var(--sm-primary-soft);
}

.sm-demo-chip strong {
  font-size: 12px;
}

.sm-demo-chip small {
  font-size: 10px;
  color: var(--sm-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-captcha-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.sm-captcha-question {
  min-width: 84px;
  padding: 6px 10px;
  border-radius: 9px;
  background: var(--sm-primary-soft);
  border: 1px dashed #c5ceff;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  text-align: center;
}

.sm-captcha-input {
  max-width: 110px;
}

.sm-login-submit {
  width: 100%;
}

.sm-login-foot {
  margin-top: 16px;
}

@media (max-width: 820px) {
  .sm-login-shell {
    grid-template-columns: 1fr;
  }

  .sm-login-aside {
    display: none;
  }

  .sm-login-card {
    padding: 24px 20px;
  }
}
</style>
