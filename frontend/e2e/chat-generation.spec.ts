import { expect, test, type Page } from '@playwright/test'

import { login } from './helpers'

/**
 * 对话页推理参数面板（课程任务书硬性要求：温度、topP、最长输出 token 数、历史轮数
 * 均可从对话页配置，且参数要真正作用于模型调用）。
 *
 * 断言链路：
 * 1) 面板打开后展示服务端默认值（GET /generation-defaults）；
 * 2) 温度拨到 0 再拨到 1，面板「当前生效」同步变化 → 证明 PATCH 落库成功；
 * 3) 刷新页面、重新打开面板，参数仍是 1（不是默认值）→ 证明按会话持久化；
 * 4) 「恢复默认」把覆盖值清空；
 * 5) 在带自定义参数的会话里提问，流式回复正常结束 → 证明参数面板不影响 SSE。
 */
test.describe('对话页推理参数面板', () => {
  /** 滑块右侧的数字输入框：填入后回车，Element Plus 会 emit change 触发 PATCH。 */
  async function setSlider(page: Page, testId: string, value: number): Promise<void> {
    const input = page.getByTestId(testId).locator('input')
    await expect(input).toBeVisible()
    await input.fill(String(value))
    await input.press('Enter')
  }

  /** 独立数字输入框（max_tokens / 历史轮数）。 */
  async function setNumber(page: Page, testId: string, value: number): Promise<void> {
    const input = page.getByTestId(testId).locator('input')
    await input.fill(String(value))
    await input.press('Enter')
  }

  test('参数按会话保存、刷新不丢，且不影响流式回复', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: '智能客服', exact: true }).click()

    // 新会话：避免复用上一轮带覆盖值的会话
    await page.getByRole('button', { name: /新对话/ }).first().click()

    const trigger = page.getByTestId('generation-params-trigger')
    await expect(trigger).toBeEnabled()
    await trigger.click()

    const panel = page.getByTestId('generation-params-panel')
    await expect(panel).toBeVisible()
    // 默认值来自后端，说明面板与服务端约定已打通（否则会显示“默认值暂不可用”）
    await expect(panel.getByTestId('gen-effective')).toContainText('温度')
    await expect(panel.getByTestId('gen-effective')).not.toContainText('默认值暂不可用')
    // 滑块轨道要有可点击宽度（曾被固定宽度的数字输入框挤成 0 宽，用户无法拖动）
    await expect(panel.getByTestId('gen-temperature').locator('.el-slider__runway')).toBeVisible()

    // 温度 1 → 0：两步都断言，证明参数值被服务端接受
    await setSlider(page, 'gen-temperature', 1)
    await expect(panel.getByTestId('gen-effective')).toContainText('温度 1')
    await expect(panel.getByTestId('gen-hint-temperature')).toHaveText('已设置')

    await setSlider(page, 'gen-temperature', 0)
    await expect(panel.getByTestId('gen-effective')).toContainText('温度 0')

    // 最长输出 512 tokens、历史 0 轮（0 轮 = 不带历史上下文）
    await setNumber(page, 'gen-max-tokens', 512)
    await expect(panel.getByTestId('gen-effective')).toContainText('512 tokens')
    await setNumber(page, 'gen-history-turns', 0)
    await expect(panel.getByTestId('gen-effective')).toContainText('历史 0 轮')
    await expect(panel.getByTestId('gen-hint-history-turns')).toHaveText('已设置')

    // 关闭面板并刷新：参数保存在会话上，不应回到默认值
    await page.locator('.sm-chat-title').click()
    await expect(panel).toBeHidden()

    await page.reload()
    await expect(page.locator('.sm-composer-input')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('generation-params-trigger').click()
    await expect(panel.getByTestId('gen-effective')).toContainText('温度 0')
    await expect(panel.getByTestId('gen-effective')).toContainText('512 tokens')
    await expect(panel.getByTestId('gen-effective')).toContainText('历史 0 轮')

    // 带自定义参数提问：流式回复正常结束（历史 0 轮 + temperature 0 都不影响 SSE 协议）
    await page.locator('.sm-chat-title').click()
    const textarea = page.locator('.sm-composer-input')
    await textarea.fill('退货期限是多久？')
    await textarea.press('Enter')
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 90_000 })
    await expect(page.locator('.sm-message-assistant').last()).toBeVisible()

    // 恢复默认：覆盖值清空，控件回到服务端默认
    await page.getByTestId('generation-params-trigger').click()
    const reset = panel.getByTestId('gen-reset')
    await expect(reset).toBeEnabled()
    await reset.click()
    await expect(panel.getByTestId('gen-hint-temperature')).toContainText('默认')
    await expect(panel.getByTestId('gen-hint-history-turns')).toContainText('默认')
    await expect(reset).toBeDisabled()

    // 刷新后确认清空也持久化了
    await page.locator('.sm-chat-title').click()
    await page.reload()
    await page.getByTestId('generation-params-trigger').click()
    await expect(panel.getByTestId('gen-hint-temperature')).toContainText('默认')
    await expect(panel.getByTestId('gen-hint-history-turns')).toContainText('默认')
  })
})
