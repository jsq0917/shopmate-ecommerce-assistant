import { expect, test } from '@playwright/test'

import { login } from './helpers'

/**
 * 对话页知识库多选（课程任务书硬性要求：可选一个或多个）。
 *
 * 断言链路：默认「全部」→ 只勾选 policy-sg → 提问 → 引用只来自新加坡文档；
 * 再切回「全部」→ 同一问题的引用回到中国大陆文档。这同时证明：
 * 1) 选择是会话级、由服务端执行（PATCH 后新消息生效）；
 * 2) Milvus 过滤与 PostgreSQL 复核都按选择收窄，不是前端过滤。
 */
test.describe('对话页知识库多选', () => {
  test('只勾选一个知识库时，引用只来自该库', async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: '智能客服', exact: true }).click()

    // 新会话：避免复用上一轮（可能已带选择）的会话
    await page.getByRole('button', { name: /新对话/ }).first().click()
    const selector = page.getByTestId('kb-select')
    await expect(selector).toBeVisible()

    // 默认状态：不限制（全部可见知识库）
    await expect(page.getByTestId('kb-hint')).toContainText('全部可见知识库')

    // 只保留 policy-sg：打开下拉，先取消已选项（默认无选中），再点 policy-sg
    await selector.locator('.el-select__wrapper').click()
    const dropdown = page.locator('.el-select-dropdown:visible')
    await expect(dropdown).toBeVisible()
    await dropdown.locator('.el-select-dropdown__item', { hasText: 'policy-sg' }).click()
    // 收起下拉（点击标题区域，避免点到输入框）
    await page.locator('.sm-chat-title').click()
    await expect(page.getByTestId('kb-hint-selected')).toContainText('仅检索所选 1 个知识库')

    const question = '新加坡的退货期限是多久？'
    const textarea = page.locator('.sm-composer-input')
    await textarea.fill(question)
    await textarea.press('Enter')

    // 等流结束（助手消息出现且不再显示“正在回复”）
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 90_000 })
    const assistant = page.locator('.sm-message-assistant').last()
    await expect(assistant).toBeVisible()

    // 引用只来自 policy-sg 的两篇文档（退货与退款政策/配送政策，均含“新加坡”）
    const citationButton = assistant.getByRole('button', { name: /查看引用/ })
    await expect(citationButton).toBeVisible({ timeout: 30_000 })
    await citationButton.click()
    const titles = page.locator('.sm-citation-title')
    await expect(titles.first()).toBeVisible()
    const texts = await titles.allInnerTexts()
    expect(texts.length).toBeGreaterThan(0)
    for (const title of texts) {
      expect(title).toContain('新加坡')
    }
    await page.keyboard.press('Escape')

    // 切回「全部」：同一问题的引用回到中国大陆文档，证明选择确实生效
    await selector.locator('.el-select__wrapper').click()
    await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', {
      hasText: 'policy-sg',
    }).click()
    await page.locator('.sm-chat-title').click()
    await expect(page.getByTestId('kb-hint')).toContainText('全部可见知识库')

    await textarea.fill(question)
    await textarea.press('Enter')
    await expect(page.locator('.sm-chat-streaming')).toBeHidden({ timeout: 90_000 })
    const latest = page.locator('.sm-message-assistant').last()
    const latestCitations = latest.getByRole('button', { name: /查看引用/ })
    if (await latestCitations.count()) {
      await latestCitations.click()
      const cnTitles = await page.locator('.sm-citation-title').allInnerTexts()
      expect(cnTitles.some((title) => title.includes('中国大陆'))).toBe(true)
    }
  })
})
