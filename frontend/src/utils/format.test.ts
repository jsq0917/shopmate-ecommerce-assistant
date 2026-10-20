import { describe, expect, it } from 'vitest'

import {
  attributeValueText,
  decisionLabel,
  formatCents,
  formatDate,
  formatDateTime,
  formatMoney,
  formatWaiting,
  handoffReasonLabel,
  newUuid,
  parseStatusLabel,
  qualityLabel,
  returnReasonLabel,
  routeLabel,
  stockStatusLabel,
  ticketStatusLabel,
} from '@/utils/format'

describe('format 工具', () => {
  describe('formatCents / formatMoney', () => {
    it('整数分格式化为人民币', () => {
      expect(formatCents(29900)).toBe('¥299.00')
      expect(formatCents(0)).toBe('¥0.00')
    })

    it('非法输入返回 --，不猜测数值', () => {
      expect(formatCents(null)).toBe('--')
      expect(formatCents(undefined)).toBe('--')
      expect(formatCents(Number.NaN)).toBe('--')
    })

    it('外币种追加币种标注', () => {
      expect(formatMoney(1999, 'USD')).toContain('USD')
      expect(formatMoney(1999, 'CNY')).not.toContain('CNY')
    })
  })

  describe('formatDateTime / formatDate', () => {
    it('ISO 时间转本地格式（与运行时本地时区一致）', () => {
      const date = new Date('2026-03-01T09:05:00Z')
      const pad = (value: number) => String(value).padStart(2, '0')
      const expectedDateTime = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
        date.getDate(),
      )} ${pad(date.getHours())}:${pad(date.getMinutes())}`
      const expectedDate = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      expect(formatDateTime('2026-03-01T09:05:00Z')).toBe(expectedDateTime)
      expect(formatDate('2026-03-01T09:05:00Z')).toBe(expectedDate)
    })

    it('空值与非法值返回 --', () => {
      expect(formatDateTime(null)).toBe('--')
      expect(formatDateTime('')).toBe('--')
      expect(formatDateTime('not-a-date')).toBe('--')
      expect(formatDate(undefined)).toBe('--')
    })
  })

  describe('formatWaiting', () => {
    it('按秒/分/小时降级显示', () => {
      expect(formatWaiting(45)).toBe('45 秒')
      expect(formatWaiting(95)).toBe('1 分钟')
      expect(formatWaiting(7200)).toBe('2 小时')
    })

    it('空值返回 --', () => {
      expect(formatWaiting(null)).toBe('--')
      expect(formatWaiting(undefined)).toBe('--')
    })
  })

  describe('状态标签映射', () => {
    it('库存', () => {
      expect(stockStatusLabel('in_stock')).toBe('有货')
      expect(stockStatusLabel('out_of_stock')).toBe('缺货')
      expect(stockStatusLabel('unknown')).toBe('库存未知')
      expect(stockStatusLabel('weird_status')).toBe('weird_status')
      expect(stockStatusLabel(null)).toBe('库存未知')
    })

    it('工单状态', () => {
      expect(ticketStatusLabel('open')).toBe('待处理')
      expect(ticketStatusLabel('assigned')).toBe('已接管')
      expect(ticketStatusLabel('resolved')).toBe('已解决')
      expect(ticketStatusLabel('closed')).toBe('已关闭')
    })

    it('路由', () => {
      expect(routeLabel('policy_faq')).toBe('政策问答')
      expect(routeLabel('return_eligibility')).toBe('退货资格')
      expect(routeLabel(null)).toBe('--')
    })

    it('退货决策与原因', () => {
      expect(decisionLabel('needs_manual_review')).toBe('需要人工审核')
      expect(returnReasonLabel('DAMAGED_ON_ARRIVAL')).toBe('到货损坏')
      expect(handoffReasonLabel('OUTPUT_GUARD_MONEY')).toBe('输出护栏：资金承诺')
    })

    it('解析状态与质量标签', () => {
      expect(parseStatusLabel('ready')).toBe('就绪')
      expect(parseStatusLabel('failed')).toBe('解析失败')
      expect(qualityLabel('needs_knowledge')).toBe('需补充知识')
    })
  })

  describe('attributeValueText', () => {
    it('未知值显示暂无数据，绝不编造', () => {
      expect(attributeValueText(null)).toBe('暂无数据')
      expect(attributeValueText(undefined)).toBe('暂无数据')
      expect(attributeValueText('')).toBe('暂无数据')
    })

    it('布尔与数字有明确展示', () => {
      expect(attributeValueText(true)).toBe('是')
      expect(attributeValueText(false)).toBe('否')
      expect(attributeValueText(42)).toBe('42')
      expect(attributeValueText({ a: 1 })).toBe('{"a":1}')
    })
  })

  describe('newUuid', () => {
    it('生成合法 UUID 且两次不同', () => {
      const first = newUuid()
      const second = newUuid()
      expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
      expect(first).not.toBe(second)
    })
  })
})
