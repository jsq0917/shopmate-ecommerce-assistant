import { expect, test, type Page } from '@playwright/test'

import { login } from './helpers'

/**
 * 为聊天流注入人为延迟，让“正在回复/停止生成”的流式状态可被稳定观测。
 * 只延迟建流时刻，事件序列与后端行为完全真实。
 */
async function slowChatStream(page: Page, delayMs = 1500): Promise<void> {
  await page.route('**/api/v1/chat/stream', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs))
    await route.continue()
  })
}

test.describe('消费者聊天页', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    // exact 避免与品牌链接（“SM ShopMate 智能客服”）的子串匹配冲突
    await page.getByRole('link', { name: '智能客服', exact: true }).click()
  })

  test('发送消息：流式过程后以服务端历史为准', async ({ page }) => {
    await slowChatStream(page)
    const question = 'e2e：退货期限是多久？'

    const textarea = page.locator('.sm-composer-input')
    await textarea.fill(question)
    await textarea.press('Enter')

    // 流进行中：展示“正在回复”与停止按钮
    await expect(page.locator('.sm-chat-streaming')).toBeVisible()
    await expect(page.getByRole('button', { name: '停止生成' })).toBeVisible()

    // 流结束后（无论 done 还是 error 事件），一律以服务端历史为准：
    // 用户消息必须出现在会话历史里。
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 60_000 })
    await expect(page.locator('.sm-message-user').filter({ hasText: question })).toBeVisible()

    // 助手消息存在：要么有回答内容，要么有明确的失败提示（不吞错）
    const assistant = page.locator('.sm-message-assistant').last()
    await expect(assistant).toBeVisible()
    const assistantText = (await assistant.innerText()).trim()
    expect(assistantText.length).toBeGreaterThan(0)
  })

  test('新建会话出现在侧栏且可发送消息', async ({ page }) => {
    // 账号可能已有历史会话（重复运行），断言增量而非绝对数量
    const before = await page.locator('.sm-conversation-item').count()
    await page.getByRole('button', { name: '新建' }).click()
    await expect(page.locator('.sm-conversation-item')).toHaveCount(before + 1)

    await slowChatStream(page)
    const textarea = page.locator('.sm-composer-input')
    await textarea.fill('你好')
    await textarea.press('Enter')
    await expect(page.locator('.sm-chat-streaming')).toBeVisible()
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 60_000 })
    await expect(page.locator('.sm-message-user').filter({ hasText: '你好' })).toBeVisible()
  })

  test('会话内联重命名', async ({ page }) => {
    await page.locator('.sm-conversation-item').first().hover()
    await page.locator('button[aria-label="重命名会话"]').first().click()
    const input = page.locator('.sm-conversation-item input')
    await input.fill('e2e-重命名会话')
    await input.press('Enter')
    await expect(page.locator('.sm-conversation-name').first()).toHaveText('e2e-重命名会话')
  })

  test('SSE 断线：显示可重试错误，重试后恢复', async ({ page }) => {
    const question = 'e2e：断线恢复演练'
    // 只中断一次建流请求，随后的重试走真实后端，验证“报错 -> 重试 -> 恢复”闭环。
    let aborted = false
    await page.route('**/api/v1/chat/stream', async (route) => {
      if (aborted) {
        await route.continue()
        return
      }
      aborted = true
      await route.abort('failed')
    })

    const textarea = page.locator('.sm-composer-input')
    await textarea.fill(question)
    await textarea.press('Enter')

    // 断线必须显式报错（不吞错），并给出重试入口。
    const alert = page.locator('.sm-bubble-error').last()
    await expect(alert).toBeVisible({ timeout: 30_000 })
    const retry = alert.getByRole('button', { name: '重试' })
    await expect(retry).toBeVisible()

    await retry.click()

    // 恢复后不再报错，用户消息入历史，助手给出回答。
    await expect(page.locator('.sm-bubble-error')).toHaveCount(0, { timeout: 60_000 })
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 60_000 })
    await expect(page.locator('.sm-message-user').filter({ hasText: question })).toBeVisible()
    const assistant = page.locator('.sm-message-assistant').last()
    await expect(assistant).toBeVisible()
    expect((await assistant.innerText()).trim().length).toBeGreaterThan(0)
  })
})
