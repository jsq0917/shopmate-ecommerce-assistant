import { expect, test } from '@playwright/test'

import { login } from './helpers'

test.describe('转人工入口', () => {
  test('聊天页转人工：创建工单并在“我的工单”可见', async ({ page }) => {
    await login(page)
    // exact 避免与品牌链接（“SM ShopMate 智能客服”）的子串匹配冲突
    await page.getByRole('link', { name: '智能客服', exact: true }).click()

    await page.getByRole('button', { name: '转人工' }).click()
    const dialog = page.locator('.el-dialog').filter({ hasText: '转人工客服' })
    await expect(dialog).toBeVisible()

    await dialog.locator('textarea').fill('e2e：希望人工确认退货政策')
    await dialog.getByRole('button', { name: '提交工单' }).click()

    // 成功展示 ticket_id（幂等键由前端生成）
    await expect(dialog.locator('.el-alert--success')).toBeVisible({ timeout: 20_000 })
    await expect(dialog.getByText('已创建人工工单')).toBeVisible()
    await expect(dialog.getByText(/工单号/)).toBeVisible()
    await dialog.getByRole('button', { name: '关闭' }).click()

    // 消费者工单列表可见该工单
    await page.getByRole('link', { name: '我的工单' }).click()
    await expect(page.locator('.el-table__row').first()).toBeVisible({ timeout: 20_000 })
    await expect(page.locator('.el-table')).toContainText('待处理')
  })
})
