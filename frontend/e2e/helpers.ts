import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { expect, type Page } from '@playwright/test'

/**
 * e2e 公共助手。
 *
 * 登录走真实 UI：读取登录页上的算式验证码并计算答案——这同时验证了
 * 登录页与 /auth/captcha 的联通，而不是绕过前端直接塞 token。
 */

const here = dirname(fileURLToPath(import.meta.url))

export interface Fixture {
  email: string
  password: string
  order_no: string
}

export function readFixture(): Fixture {
  return JSON.parse(readFileSync(join(here, '.fixture.json'), 'utf-8')) as Fixture
}

/** 计算算式验证码答案，如 "3 + 5 = ?" -> "8"。 */
function solveCaptcha(question: string): string {
  const match = /(\d+)\s*\+\s*(\d+)/.exec(question)
  if (!match) throw new Error(`无法解析验证码题目：${question}`)
  return String(Number(match[1]) + Number(match[2]))
}

/** 通过登录页完成登录，落地到首页。 */
export async function login(page: Page, fixture: Fixture = readFixture()): Promise<void> {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'ShopMate 电商智能客服' })).toBeVisible()

  // 登录/注册两个 Tab 面板都在 DOM 中，只操作可见面板，避免 strict mode 冲突
  const loginPane = page.locator('.el-tab-pane:not([style*="display: none"])')
  // 验证码是异步加载的，先等题目就绪，避免读到“加载中…”导致答案计算失败
  const questionLocator = loginPane.locator('.sm-captcha-question')
  await expect(questionLocator).toHaveText(/\d+\s*\+\s*\d+/, { timeout: 15_000 })
  const answer = solveCaptcha(await questionLocator.innerText())

  await loginPane.locator('input[type="email"]').fill(fixture.email)
  await loginPane.locator('input[type="password"]').fill(fixture.password)
  await loginPane.locator('.sm-captcha-input input').fill(answer)
  await page.getByRole('button', { name: '登录', exact: true }).click()

  // 登录成功后必须真正进入首页（商品中心导航未登录也可见，不能单独作为判据）
  await expect(page.getByRole('link', { name: '商品中心' })).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.sm-composer-input')).toBeVisible({ timeout: 20_000 })
  await expect(page).not.toHaveURL(/\/login/)
}

/** 未登录访问受保护页面时应重定向到登录页。 */
export async function expectRedirectToLogin(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await expect(page.getByRole('heading', { name: 'ShopMate 电商智能客服' })).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
}
