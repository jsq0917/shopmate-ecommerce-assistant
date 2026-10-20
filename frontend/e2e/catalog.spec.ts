import { expect, test } from '@playwright/test'

import { login } from './helpers'

test.describe('商品中心', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.getByRole('link', { name: '商品中心' }).click()

    // 商品搜索接口要求关键词非空，进入页面不自动搜索
    await page.locator('.sm-filters input').first().fill('耳机')
    await page.getByRole('button', { name: '搜索' }).click()
    await expect(page.locator('.sm-product-card').first()).toBeVisible({ timeout: 20_000 })
  })

  test('空关键词不发起请求并给出提示', async ({ page }) => {
    await page.locator('.sm-filters input').first().fill('')
    await page.getByRole('button', { name: '搜索' }).click()
    // ElMessage 警告 + 不发请求（无错误横幅）
    await expect(page.locator('.el-message--warning')).toBeVisible()
    await expect(page.locator('.el-alert--error')).toHaveCount(0)
  })

  test('搜索展示商品卡片：价格、库存与数据时间', async ({ page }) => {
    const firstCard = page.locator('.sm-product-card').first()
    // 价格必须来自 API（¥ 格式），不允许为空
    await expect(firstCard.locator('.sm-product-price')).toHaveText(/^¥[\d,.]+$/)
    // 库存标签
    await expect(firstCard.locator('.sm-product-stock')).toHaveText(/有货|缺货|库存未知/)
    // 数据更新时间
    await expect(firstCard.locator('.sm-as-of')).toContainText('数据更新时间')
  })

  test('2-4 件商品对齐比较，unknown 表示缺失而非推测', async ({ page }) => {
    await page.locator('.sm-product-card').nth(0).locator('.el-checkbox').click()
    await page.locator('.sm-product-card').nth(1).locator('.el-checkbox').click()
    await page.getByRole('button', { name: '开始比较' }).click()

    const table = page.locator('.sm-compare-table')
    await expect(table).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('商品比较（2 件）')).toBeVisible()
    // 对比项列 + 2 件商品列
    const columns = await table.locator('thead th').count()
    expect(columns).toBeGreaterThanOrEqual(3)
    // 明确告知 unknown 语义
    await expect(page.getByText(/unknown 表示数据库中没有该字段/)).toBeVisible()
  })

  test('商品详情展示变体与库存', async ({ page }) => {
    await page.locator('.sm-product-card').first().getByRole('button', { name: '详情/库存' }).click()
    const dialog = page.locator('.el-dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('.el-table')).toBeVisible()
    await dialog.getByRole('button', { name: '关闭' }).click()
    await expect(dialog).toBeHidden()
  })
})
