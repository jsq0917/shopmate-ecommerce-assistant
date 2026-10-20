/**
 * 本地 e2e fixture（一次性、幂等）：
 * 1. 通过公开 API 注册演示买家账号（验证码为算式题，答案可由题干计算）；
 * 2. 通过本地 PG 容器插入一条 delivered 订单 + 订单行 + 物流轨迹（合成数据）。
 *
 * 用法（API 已启动后）：
 *   node e2e/fixture.mjs
 * 环境变量：
 *   E2E_API_BASE   默认 http://127.0.0.1:18001/api/v1
 *   E2E_SHOPPER_EMAIL / E2E_SHOPPER_PASSWORD
 *
 * 说明：只写本地开发库；不提交任何凭据。重复执行不会重复建单。
 */

import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const API_BASE = process.env.E2E_API_BASE ?? 'http://127.0.0.1:18001/api/v1'
const EMAIL = process.env.E2E_SHOPPER_EMAIL ?? 'e2e.shopper@example.invalid'
const PASSWORD = process.env.E2E_SHOPPER_PASSWORD ?? 'shopmate-e2e-demo'
const PG_CONTAINER = process.env.E2E_PG_CONTAINER ?? 'shopmate-postgres-1'

/** 计算算式验证码答案，如 "3 + 5 = ?" -> "8"。 */
function solveCaptcha(question) {
  const match = /(\d+)\s*\+\s*(\d+)/.exec(question)
  if (!match) throw new Error(`无法解析验证码题目：${question}`)
  return String(Number(match[1]) + Number(match[2]))
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
  })
  const body = await response.json().catch(() => null)
  return { status: response.status, body }
}

function psql(sql) {
  return execFileSync('docker', ['exec', '-i', PG_CONTAINER, 'psql', '-U', 'shopmate', '-d', 'shopmate', '-v', 'ON_ERROR_STOP=1', '-q', '-t', '-A'], {
    input: sql,
    encoding: 'utf-8',
  })
}

async function waitForApi(timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    try {
      const response = await fetch(`${API_BASE.replace(/\/api\/v1$/, '')}/health`)
      if (response.ok) return
    } catch {
      // 继续等待
    }
    if (Date.now() > deadline) throw new Error(`API 在 ${timeoutMs}ms 内未就绪：${API_BASE}`)
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}

async function registerShopper() {
  const captcha = await api('/auth/captcha')
  if (captcha.status !== 200 || !captcha.body?.data?.captcha_token) {
    throw new Error(`获取验证码失败：${JSON.stringify(captcha.body)}`)
  }
  const result = await api('/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      email: EMAIL,
      password: PASSWORD,
      captcha_token: captcha.body.data.captcha_token,
      captcha_answer: solveCaptcha(captcha.body.data.question),
    }),
  })
  if (result.status === 201) {
    console.log(`[fixture] 已注册演示账号 ${EMAIL}`)
    return
  }
  if (result.status === 400 && result.body?.error?.code === 'VALIDATION_ERROR') {
    console.log(`[fixture] 账号已存在（${EMAIL}），跳过注册`)
    return
  }
  throw new Error(`注册失败：${result.status} ${JSON.stringify(result.body)}`)
}

async function verifyLogin() {
  const captcha = await api('/auth/captcha')
  const result = await api('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email: EMAIL,
      password: PASSWORD,
      captcha_token: captcha.body.data.captcha_token,
      captcha_answer: solveCaptcha(captcha.body.data.question),
    }),
  })
  if (result.status !== 200) {
    throw new Error(`登录校验失败：${result.status} ${JSON.stringify(result.body)}`)
  }
  console.log('[fixture] 登录校验通过')
}

/** 清理上一次 e2e 运行产生的写操作记录，保证资格检查等断言可重复。 */
const RESET_SQL = `
DELETE FROM return_requests rr
USING orders o
WHERE rr.order_id = o.id AND o.order_no LIKE 'E2E-%';

DELETE FROM handoff_tickets ht
USING users u
WHERE ht.user_id = u.id AND u.email_ci = lower('${EMAIL}');
`

const ORDER_SQL = `
WITH u AS (
  SELECT id, shop_id FROM users WHERE email_ci = lower('${EMAIL}')
),
existing AS (
  SELECT count(*)::int AS n
  FROM orders o JOIN u ON o.shop_id = u.shop_id AND o.user_id = u.id
  WHERE o.order_no LIKE 'E2E-%'
),
v AS (
  SELECT pv.id AS variant_id, pv.sku, p.title, p.category
  FROM product_variants pv JOIN products p ON p.id = pv.product_id
  ORDER BY p.created_at, pv.created_at
  LIMIT 1
),
ins_order AS (
  INSERT INTO orders (id, shop_id, user_id, order_no, status, total_cents, currency, placed_at, delivered_at, shipping_address_masked)
  SELECT gen_random_uuid(), u.shop_id, u.id,
         'E2E-' || to_char(now(), 'YYYYMMDDHH24MISSUS'),
         'delivered', 29900, 'CNY',
         now() - interval '12 days', now() - interval '4 days',
         '*** 市 *** 区 *** 路 1 号'
  FROM u, v, existing
  WHERE existing.n = 0
  RETURNING id, shop_id
)
INSERT INTO order_items (id, shop_id, order_id, variant_id, sku_snapshot, title_snapshot, category_snapshot, is_returnable_snapshot, quantity, unit_price_cents, line_total_cents, status, delivered_at)
SELECT gen_random_uuid(), i.shop_id, i.id, v.variant_id, v.sku, v.title, v.category, true, 1, 29900, 29900, 'active', now() - interval '4 days'
FROM ins_order i, v;
`

const SHIPMENT_SQL = `
WITH s AS (
  INSERT INTO shipments (id, shop_id, order_id, carrier, tracking_no_masked, status, shipped_at, estimated_delivery_at, delivered_at)
  SELECT gen_random_uuid(), o.shop_id, o.id, '顺丰速运', 'SF1234****89', 'delivered'::shipment_status,
         now() - interval '11 days', now() - interval '3 days', now() - interval '4 days'
  FROM orders o
  WHERE o.order_no LIKE 'E2E-%'
    AND NOT EXISTS (SELECT 1 FROM shipments sh WHERE sh.order_id = o.id)
  RETURNING id, shop_id
),
no_event_shipping AS (
  -- 覆盖“物流已创建但事件未写入”的半成品状态，保证整体幂等
  SELECT sh.id, sh.shop_id
  FROM shipments sh JOIN orders o ON o.id = sh.order_id
  WHERE o.order_no LIKE 'E2E-%'
    AND NOT EXISTS (SELECT 1 FROM shipment_events se WHERE se.shipment_id = sh.id)
)
INSERT INTO shipment_events (id, shop_id, shipment_id, sequence_no, status, description, occurred_at)
SELECT gen_random_uuid(), n.shop_id, n.id, 1, 'picked_up'::shipment_status, '包裹已揽收', now() - interval '11 days' FROM no_event_shipping n
UNION ALL
SELECT gen_random_uuid(), n.shop_id, n.id, 2, 'in_transit'::shipment_status, '运输中', now() - interval '8 days' FROM no_event_shipping n
UNION ALL
SELECT gen_random_uuid(), n.shop_id, n.id, 3, 'delivered'::shipment_status, '已签收', now() - interval '4 days' FROM no_event_shipping n;
`

async function seedOrder() {
  psql(ORDER_SQL)
  psql(SHIPMENT_SQL)
  const orderNo = psql(
    `SELECT o.order_no FROM orders o JOIN users u ON o.shop_id = u.shop_id AND o.user_id = u.id ` +
      `WHERE u.email_ci = lower('${EMAIL}') AND o.order_no LIKE 'E2E-%' ORDER BY o.placed_at DESC LIMIT 1;`,
  ).trim()
  if (!orderNo) throw new Error('未找到 e2e 订单，SQL 插入失败')
  console.log(`[fixture] 演示订单就绪：${orderNo}`)
  return orderNo
}

async function main() {
  await waitForApi()
  await registerShopper()
  await verifyLogin()
  psql(RESET_SQL)
  const orderNo = await seedOrder()
  const fixture = { email: EMAIL, password: PASSWORD, order_no: orderNo }
  writeFileSync(join(here, '.fixture.json'), `${JSON.stringify(fixture, null, 2)}\n`, 'utf-8')
  console.log('[fixture] 已写入 e2e/.fixture.json')
}

main().catch((error) => {
  console.error(`[fixture] 失败：${error.message}`)
  process.exit(1)
})
