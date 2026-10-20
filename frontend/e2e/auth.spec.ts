import { expect, test } from '@playwright/test'

import { expectRedirectToLogin, login, readFixture } from './helpers'

test.describe('认证与路由守卫', () => {
  test('未登录访问受保护页面重定向到登录页', async ({ page }) => {
    await expectRedirectToLogin(page, '/orders')
    await expectRedirectToLogin(page, '/products')
    await expectRedirectToLogin(page, '/support')
  })

  test('错误密码展示稳定错误文案且停留在登录页', async ({ page }) => {
    const fixture = readFixture()
    await page.goto('/login')

    // 登录/注册两个 Tab 面板都在 DOM 中，只操作可见面板，避免 strict mode 冲突
    const loginPane = page.locator('.el-tab-pane:not([style*="display: none"])')
    // 验证码异步加载，先等题目就绪，避免读到“加载中…”
    const questionLocator = loginPane.locator('.sm-captcha-question')
    await expect(questionLocator).toHaveText(/\d+\s*\+\s*\d+/, { timeout: 15_000 })
    const question = await questionLocator.innerText()
    const answer = String(
      /(\d+)\s*\+\s*(\d+)/.exec(question)!.slice(1).reduce((sum, part) => sum + Number(part), 0),
    )

    await loginPane.locator('input[type="email"]').fill(fixture.email)
    await loginPane.locator('input[type="password"]').fill('wrong-password-xyz')
    await loginPane.locator('.sm-captcha-input input').fill(answer)
    await page.getByRole('button', { name: '登录', exact: true }).click()

    await expect(page.locator('.el-alert--error')).toContainText('邮箱或密码不正确')
    await expect(page).toHaveURL(/\/login/)
  })

  test('正确凭据登录进入消费者首页', async ({ page }) => {
    await login(page)
    // 收紧断言：旧的 /\/(\?.*)?$/ 会让被弹回的 `/login?next=/` 也算通过
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('.sm-composer-input')).toBeVisible()
    // 合成数据横幅必须可见（演示环境提示，文案与 AppShell 保持一致）
    await expect(page.getByText('合成演示数据').first()).toBeVisible()
    // 消费者端不展示客服/管理入口
    await expect(page.getByRole('link', { name: '客服工作台' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: '管理后台' })).toHaveCount(0)
  })

  test('刷新页面后保持登录（静默刷新）', async ({ page }) => {
    await login(page)
    await page.reload()
    await expect(page.getByRole('link', { name: '商品中心' })).toBeVisible({ timeout: 20_000 })
    // 该导航链接未登录也可见，必须再断言首页真实元素才算真的保持登录
    await expect(page.locator('.sm-composer-input')).toBeVisible({ timeout: 20_000 })
    await expect(page).not.toHaveURL(/\/login/)
  })
})
