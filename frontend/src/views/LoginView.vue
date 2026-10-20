<script setup lang="ts">
/**
 * 登录 / 注册。验证码由 GET /auth/captcha 提供（算式题，答案在服务端签名，
 * 前端不存储明文）。access token 只进内存，刷新依赖 HttpOnly cookie。
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

async function onLogin(): Promise<void> {
  if (!canSubmitLogin.value || loading.value) return
  loading.value = true
  error.value = null
  notice.value = ''
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
    // 与 onLogin 同样处理：先留住错误，再刷新验证码，避免提示被清空。
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
    <div class="sm-login-card sm-card">
      <h1 class="sm-login-title">ShopMate 电商智能客服</h1>
      <p class="sm-muted">登录后可查询商品、政策、订单与售后进度。演示环境使用合成数据。</p>

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
                <ElButton size="small" @click="loadCaptcha">刷新</ElButton>
              </div>
            </ElFormItem>
            <ElButton type="primary" :loading="loading" :disabled="!canSubmitLogin" @click="onLogin">
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
                <ElButton size="small" @click="loadCaptcha">刷新</ElButton>
              </div>
            </ElFormItem>
            <ElButton type="primary" :loading="loading" :disabled="!canSubmitRegister" @click="onRegister">
              注册
            </ElButton>
          </ElForm>
        </ElTabPane>
      </ElTabs>

      <p class="sm-muted sm-login-foot">
        客服与管理员账号由运营分配；消费者注册后默认进入消费者端。
      </p>
    </div>
  </div>
</template>

<style scoped>
.sm-login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
  background: linear-gradient(160deg, #eef5f0 0%, #f4f7f5 60%);
}

.sm-login-card {
  width: min(26rem, 100%);
}

.sm-login-title {
  margin: 0 0 4px;
  font-size: 20px;
}

.sm-login-alert {
  margin: 12px 0;
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
  border-radius: 8px;
  background: var(--sm-bg);
  border: 1px dashed var(--sm-border);
  font-family: ui-monospace, Menlo, Consolas, monospace;
}

.sm-captcha-input {
  max-width: 120px;
}

.sm-login-foot {
  margin-top: 16px;
}
</style>
