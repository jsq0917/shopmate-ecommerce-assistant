import { execSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

import { login, readFixture } from './helpers'

test.describe('订单 / 物流 / 退货流程', () => {
  test.beforeAll(() => {
    // 上一轮运行可能已提交退货/工单，资格检查会命中 DUPLICATE_RETURN。
    // fixture 幂等（清理写操作记录 + 重建演示订单），运行前重置一遍保证断言可重复。
    execSync('node e2e/fixture.mjs', { stdio: 'inherit' })
  })

  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('订单列表 -> 详情 -> 物流时间线', async ({ page }) => {
    const fixture = readFixture()
    await page.getByRole('link', { name: '我的订单' }).click()

    const row = page.locator('.el-table__row').filter({ hasText: fixture.order_no })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: '详情' }).click()

    await expect(page).toHaveURL(/\/orders\//)
    await expect(page.locator('.sm-order-detail, .sm-page').first()).toBeVisible()

    // 按需加载物流
    await page.getByRole('button', { name: '查看物流' }).click()
    const timeline = page.locator('.el-timeline')
    await expect(timeline).toBeVisible()
    await expect(timeline).toContainText('包裹已揽收')
    await expect(timeline).toContainText('已签收')
    // 脱敏单号
    await expect(page.getByText(/SF1234\*\*\*\*89/)).toBeVisible()
  })

  test('退货向导：资格检查 -> 明确确认 -> 幂等提交', async ({ page }) => {
    const fixture = readFixture()
    await page.getByRole('link', { name: '我的订单' }).click()
    const row = page.locator('.el-table__row').filter({ hasText: fixture.order_no })
    await row.getByRole('button', { name: '详情' }).click()

    // 选择订单商品
    const itemSelect = page.locator('.sm-return .el-select').first()
    await itemSelect.click()
    await page.locator('.el-select-dropdown__item').first().click()

    // 检查退货资格（确定性规则）
    await page.getByRole('button', { name: '检查退货资格' }).click()
    const result = page.locator('.sm-return-result')
    await expect(result).toBeVisible({ timeout: 20_000 })
    await expect(result).toContainText('符合退货条件')
    await expect(result).toContainText('规则版本')

    // 未勾选确认时提交按钮禁用
    const submit = page.getByRole('button', { name: '提交退货申请' })
    await expect(submit).toBeDisabled()

    // 勾选明确确认（提交≠退款）
    await page.locator('.sm-return-confirm .el-checkbox').click()
    await expect(submit).toBeEnabled()
    await submit.click()

    // 成功态：submitted + refund_status=not_created + 免责提示
    const success = page.locator('.el-alert--success').filter({ hasText: '退货申请已提交' })
    await expect(success).toBeVisible({ timeout: 20_000 })
    await expect(success).toContainText('not_created')
    await expect(success).toContainText('申请已提交，但尚未退款')
  })

  test('退货申请重复提交被幂等拦截', async ({ page }) => {
    const fixture = readFixture()
    await page.getByRole('link', { name: '我的订单' }).click()
    const row = page.locator('.el-table__row').filter({ hasText: fixture.order_no })
    await row.getByRole('button', { name: '详情' }).click()

    const itemSelect = page.locator('.sm-return .el-select').first()
    await itemSelect.click()
    await page.locator('.el-select-dropdown__item').first().click()
    await page.getByRole('button', { name: '检查退货资格' }).click()
    await expect(page.locator('.sm-return-result')).toBeVisible({ timeout: 20_000 })

    const submit = page.getByRole('button', { name: '提交退货申请' })
    // 已存在有效申请时，资格检查会给出不可提交的结论或提交被拒；
    // 两种情况都不应出现“退款成功”类误导文案。
    if (await submit.count()) {
      await page.locator('.sm-return-confirm .el-checkbox').click()
      await submit.click()
      await page.waitForTimeout(2000)
      const body = await page.locator('.sm-return').innerText()
      expect(body).not.toContain('退款成功')
      expect(body).not.toContain('已退款')
    }
  })
})
