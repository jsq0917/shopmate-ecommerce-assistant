# ShopMate 工具契约

> 阶段：阶段 3 — 架构、数据契约、工具契约与 API 契约  
> 版本：v1.0  
> 日期：2026-10-18  
> 状态：逻辑工具契约；不代表工具已经实现  
> 关联：`docs/03-architecture.md`、`docs/04-data-contract.md`、`docs/07-security.md`

## 1. 工具边界

工具是模型与业务系统之间唯一的受控桥梁。模型只能调用本文件登记的 10 个工具；工具注册表执行严格 schema、身份注入、权限、资源归属、业务状态、幂等和审计。模型不能：

- 直接访问 PostgreSQL、Redis、Milvus、Mock OMS 或任意 URL。
- 传入、修改或覆盖 `shop_id`、`user_id`、角色、客服身份、审批人、退款状态或内部审计字段。
- 调用未注册工具、动态 SQL、任意函数名或临时生成的管理员工具。
- 用自然语言“已批准”“已退款”改变工具结果或业务状态。

## 2. 执行上下文与调用顺序

工具 schema 只描述调用者可提供的业务参数。以下 `ToolContext` 由后端注入，模型不可见也不可覆盖：

```text
ToolContext {
  request_id: UUID,
  trace_id: UUID,
  conversation_id: UUID,
  actor_user_id: UUID,
  effective_user_id: UUID,
  shop_id: UUID,
  role: shopper | support | admin,
  permissions: string[],
  risk_context: { level, rule_codes[] },
  confirmation_state: { verified, operation, expires_at } | null,
  action_budget: { used, remaining }
}
```

固定执行顺序：

1. 严格校验输入 schema，拒绝未知字段、错误类型和越界值。
2. 从认证上下文注入身份和店铺范围，不接受 payload 中的身份覆盖。
3. 校验角色权限。
4. 校验资源存在性与用户/店铺归属。对用户资源，不存在与越权对外使用同一安全错误。
5. 校验业务状态、有效期、风险和幂等条件。
6. 在事务中执行读取或写入。
7. 写最小化审计记录并返回统一信封。

## 3. 统一结果信封

### 3.1 成功

```json
{
  "ok": true,
  "contract_version": "1.0",
  "tool_call_id": "7f86e1a2-cc90-4d71-8de4-c44678bd58db",
  "data": {},
  "source": "postgres",
  "as_of": "2026-10-18T12:00:00Z",
  "trace_id": "4ca84ec8-a5f1-4f16-a1aa-d50b2bbbb0eb",
  "idempotent_replay": false
}
```

- `source`：`postgres | redis | mock_oms | rule_engine | milvus`。
- 读工具必须返回 `as_of`；写工具返回业务时间与资源状态。
- `idempotent_replay` 只对写工具有意义；非幂等工具固定为 `false`。

### 3.2 失败

```json
{
  "ok": false,
  "contract_version": "1.0",
  "tool_call_id": "7f86e1a2-cc90-4d71-8de4-c44678bd58db",
  "error_code": "ORDER_NOT_FOUND",
  "user_message": "未找到可由当前账号访问的订单。请核对订单号，或转人工协助。",
  "retryable": false,
  "retry_after_ms": null,
  "trace_id": "4ca84ec8-a5f1-4f16-a1aa-d50b2bbbb0eb"
}
```

禁止在信封中返回堆栈、SQL、数据库连接串、内部 token、完整 PII、未脱敏订单地址或其他用户字段。

## 4. 错误码目录

| 错误码 | 含义 | 可重试 | 典型处理 |
|---|---|---:|---|
| `VALIDATION_ERROR` | schema/枚举/范围错误 | 否 | 澄清或修正参数 |
| `FORBIDDEN` | 角色或操作无权限 | 否 | 审计并统一拒绝 |
| `PRODUCT_NOT_FOUND` | 商品或可售变体不存在 | 否 | 不生成替代商品 |
| `VARIANT_NOT_FOUND` | SKU/变体不存在 | 否 | 要求重新选择 |
| `ORDER_NOT_FOUND` | 订单不存在或不可由当前用户访问 | 否 | 不泄露存在性，可转人工 |
| `SHIPMENT_NOT_FOUND` | 订单无可访问物流记录 | 否 | 说明当前无法确认 |
| `CONVERSATION_NOT_FOUND` | 会话不存在或不属于当前用户 | 否 | 不泄露存在性 |
| `OUT_OF_STOCK` | 请求数量超过可售库存 | 是（稍后） | 返回真实数量 |
| `INVALID_STATE` | 当前业务状态不允许操作 | 否 | 解释状态和下一步 |
| `RETURN_NOT_ALLOWED` | 商品/原因/订单状态不允许自动申请 | 否 | 解释规则或人工 |
| `RETURN_WINDOW_EXPIRED` | 超过签收后 7 天窗口 | 否 | 返回截止时间，可人工申诉 |
| `DUPLICATE_RETURN` | 同一订单项已存在任一有效退货申请 | 否 | 返回原申请或冲突摘要 |
| `MANUAL_REVIEW_REQUIRED` | 原因或金额要求人工审核 | 否 | 自动升级人工，不创建自动申请 |
| `LOW_CONFIDENCE` | 意图、实体或证据不足以安全判定 | 是可重试 | 先澄清；重复命中或涉及权益时转人工 |
| `CONFIRMATION_REQUIRED` | 缺少用户明确确认 | 是（确认后） | 询问是否提交 |
| `ELIGIBILITY_EXPIRED` | 资格令牌失效或状态已变化 | 是（重查） | 重新执行资格检查 |
| `IDEMPOTENCY_CONFLICT` | 同一幂等键对应不同请求 | 否 | 提示使用新请求或查看原结果 |
| `IDEMPOTENCY_IN_PROGRESS` | 相同请求仍在处理中 | 是（短间隔） | 不并发创建第二资源 |
| `TOOL_BUDGET_EXCEEDED` | 超出单轮调用预算 | 否 | 停止并给出下一步 |
| `RISK_HANDOFF_REQUIRED` | 风险规则要求人工 | 否 | 创建/展示人工路径 |
| `UPSTREAM_UNAVAILABLE` | 受控上游不可用 | 是 | 返回无法确认，不猜测事实 |
| `RATE_LIMITED` | 超过限流 | 是 | 返回安全的 `retry_after_ms` |
| `INTERNAL_ERROR` | 未分类内部错误 | 视情况 | 记录 trace，返回安全提示 |

同一工具连续失败 2 次后停止重试。工具结果与模型陈述冲突时以工具结果为准；资金承诺或事实冲突可触发 `RISK_HANDOFF_REQUIRED`。

## 5. 10 个工具契约

### 5.1 `search_products`

**输入**

```json
{
  "query": "预算 300 元以内、适合通勤的降噪耳机",
  "category": "耳机",
  "brand": null,
  "budget_min_cents": null,
  "budget_max_cents": 30000,
  "attributes": {
    "noise_cancellation": true,
    "use_case": "commute"
  },
  "in_stock_only": false,
  "limit": 10
}
```

约束：`query` 1-200 字符；`category/brand` 各最多 80 字符；预算为非负整数分且 min <= max；属性最多 10 个白名单键；`limit` 1-20。`0` 是合法金额边界。

**输出 `data`**

```json
{
  "items": [
    {
      "product_id": "uuid",
      "variant_id": "uuid",
      "title": "示例降噪耳机",
      "brand": "示例品牌",
      "category": "耳机",
      "sku": "DEMO-HEAD-001",
      "price_cents": 29900,
      "currency": "CNY",
      "stock_status": "in_stock",
      "available_qty": 12,
      "attributes": {"noise_cancellation": true, "use_case": "commute"},
      "matched_reasons": ["预算内", "属性匹配"],
      "image_url": null,
      "is_synthetic": true,
      "as_of": "2026-10-18T12:00:00Z"
    }
  ],
  "truncated": false
}
```

`stock_status` 为 `in_stock/out_of_stock/unknown`；未知属性不补写。

**权限与副作用**：登录且属于当前店铺的用户；只读。  
**错误码**：`VALIDATION_ERROR`、`FORBIDDEN`、`UPSTREAM_UNAVAILABLE`、`RATE_LIMITED`。  
**幂等**：无写副作用；同一查询可重复执行。

### 5.2 `get_product_detail`

**输入**

```json
{
  "product_id": "uuid",
  "variant_id": "uuid-or-null"
}
```

**输出 `data`**

```json
{
  "product": {
    "id": "uuid",
    "title": "示例降噪耳机",
    "description": "合成商品说明",
    "brand": "示例品牌",
    "category": "耳机",
    "attributes": {"noise_cancellation": true},
    "status": "active",
    "is_synthetic": true,
    "variants": [
      {
        "id": "uuid",
        "sku": "DEMO-HEAD-001-BLK",
        "title": "黑色",
        "attributes": {"color": "black"},
        "price_cents": 29900,
        "currency": "CNY",
        "status": "active",
        "available_qty": 12,
        "stock_updated_at": "2026-10-18T11:59:30Z"
      }
    ]
  }
}
```

**权限与副作用**：登录用户、当前店铺；只读。  
**错误码**：`PRODUCT_NOT_FOUND`、`VARIANT_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.3 `compare_products`

**输入**

```json
{
  "product_ids": ["uuid", "uuid"],
  "attributes": ["price", "noise_cancellation", "battery_hours"]
}
```

约束：2-4 个唯一商品 ID；`attributes` 最多 20 个受控维度。

**输出 `data`**

```json
{
  "products": [
    {"product_id": "uuid", "title": "商品 A", "variant_id": "uuid"},
    {"product_id": "uuid", "title": "商品 B", "variant_id": "uuid"}
  ],
  "rows": [
    {
      "key": "price",
      "label": "价格",
      "values": [
        {"product_id": "uuid", "known": true, "value": 29900, "unit": "CNY_cents"},
        {"product_id": "uuid", "known": true, "value": 32900, "unit": "CNY_cents"}
      ]
    },
    {
      "key": "battery_hours",
      "label": "续航",
      "values": [
        {"product_id": "uuid", "known": false, "value": null, "unit": null},
        {"product_id": "uuid", "known": true, "value": 30, "unit": "hour"}
      ]
    }
  ]
}
```

缺失字段必须 `known=false,value=null`，不得推断。

**权限与副作用**：登录用户、当前店铺；只读。  
**错误码**：`VALIDATION_ERROR`、`PRODUCT_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.4 `check_stock`

**输入**

```json
{
  "variant_id": "uuid",
  "quantity": 1
}
```

`quantity` 为 1-999 的整数。

**输出 `data`**

```json
{
  "variant_id": "uuid",
  "requested_qty": 1,
  "available_qty": 12,
  "is_available": true,
  "warehouses": [
    {
      "warehouse_code": "DEMO-WH-01",
      "available_qty": 12,
      "updated_at": "2026-10-18T11:59:30Z"
    }
  ]
}
```

**权限与副作用**：登录用户、当前店铺；只读。  
**缺货表达**：可售数量小于 `quantity` 时仍返回成功信封，`is_available=false` 并给出数据库中的真实 `available_qty` 与仓库明细；不把缺货包装成有货，也不用失败信封隐藏真实数量。`OUT_OF_STOCK` 保留给后续写路径（预留、下单）使用。  
**错误码**：`VALIDATION_ERROR`、`VARIANT_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.5 `get_promotion`

**输入**

```json
{
  "product_id": "uuid",
  "variant_id": "uuid-or-null",
  "at": "2026-10-18T12:00:00Z-or-null"
}
```

`at` 缺省为服务端当前 UTC 时间。工具只返回适用于指定时间和范围的合成活动，不承诺未生效活动。

**输出 `data`**

```json
{
  "product_id": "uuid",
  "variant_id": "uuid",
  "applicable": true,
  "promotions": [
    {
      "promotion_id": "uuid",
      "name": "合成通勤季",
      "rule_summary": "满 29900 分减 2000 分",
      "starts_at": "2026-10-01T00:00:00Z",
      "ends_at": "2026-10-31T15:59:59Z",
      "status": "active"
    }
  ],
  "evaluated_at": "2026-10-18T12:00:00Z"
}
```

**权限与副作用**：登录用户、当前店铺；只读。  
**错误码**：`PRODUCT_NOT_FOUND`、`VARIANT_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.6 `get_order_status`

**输入**（`order_id` 与 `order_no` 二选一）

```json
{
  "order_id": "uuid",
  "order_no": null
}
```

**后端归属规则**：查询同时使用 `shop_id` 和 `effective_user_id`。订单不存在、属于其他用户或属于其他店铺均返回相同 `ORDER_NOT_FOUND`，不返回任何订单字段。

**输出 `data`**

```json
{
  "order_id": "uuid",
  "order_no": "DEMO-1001",
  "status": "shipped",
  "total_cents": 29900,
  "currency": "CNY",
  "is_synthetic": true,
  "placed_at": "2026-10-15T02:00:00Z",
  "status_updated_at": "2026-10-17T01:00:00Z",
  "timeline": [
    {"status": "paid", "occurred_at": "2026-10-15T02:01:00Z"},
    {"status": "shipped", "occurred_at": "2026-10-17T01:00:00Z"}
  ]
}
```

**权限与副作用**：仅当前认证用户的本人订单；客服只能通过授权工单看到已存在的安全工具摘要，不能把他人用户 ID 作为参数。只读。  
**错误码**：`VALIDATION_ERROR`、`ORDER_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.7 `get_shipment`

**输入**

```json
{
  "order_id": "uuid"
}
```

**后端归属规则**：先按 `shop_id/effective_user_id/order_id` 验证订单归属，再查询该订单物流；任何一步不匹配均返回 `ORDER_NOT_FOUND` 或统一安全错误，不泄露物流是否存在。

**输出 `data`**

```json
{
  "order_id": "uuid",
  "shipment_id": "uuid",
  "carrier": "示例承运商",
  "tracking_no_masked": "DEMO****1001",
  "status": "in_transit",
  "is_synthetic": true,
  "shipped_at": "2026-10-17T01:00:00Z",
  "estimated_delivery_at": "2026-10-20T10:00:00Z",
  "delivered_at": null,
  "status_updated_at": "2026-10-18T03:00:00Z",
  "events": [
    {
      "status": "in_transit",
      "description": "已离开示例分拨中心",
      "occurred_at": "2026-10-18T03:00:00Z"
    }
  ]
}
```

**权限与副作用**：仅当前用户本人订单；只读。  
**错误码**：`ORDER_NOT_FOUND`、`SHIPMENT_NOT_FOUND`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：只读。

### 5.8 `check_return_eligibility`

**输入**

```json
{
  "order_id": "uuid",
  "order_item_id": "uuid",
  "reason_code": "SIZE_OR_FIT"
}
```

`reason_code`：`SIZE_OR_FIT | NO_LONGER_NEEDED | DAMAGED_ON_ARRIVAL | WRONG_ITEM | QUALITY_ISSUE | OTHER`。

**输出 `data`**

```json
{
  "decision": "eligible",
  "decision_code": "RETURN_ELIGIBLE",
  "error_code": null,
  "eligible": true,
  "needs_clarification": false,
  "needs_manual_review": false,
  "can_create_return_request": true,
  "handoff_required": false,
  "matched_rule_codes": [
    "ORDER_DELIVERED",
    "ITEM_RETURNABLE",
    "REASON_IN_WINDOW",
    "WITHIN_7_DAYS"
  ],
  "deadline_at": "2026-10-24T08:00:00Z",
  "rule_version": "demo-return-v1",
  "required_materials": ["商品及包装完好", "退货原因说明"],
  "next_action": "confirm_to_submit",
  "eligibility_token": "opaque-signed-token",
  "eligibility_expires_at": "2026-10-18T12:10:00Z",
  "evaluated_at": "2026-10-18T12:00:00Z"
}
```

`decision` 为 `eligible/ineligible/needs_clarification/needs_manual_review`。`decision_code` 是稳定业务结果码；`error_code` 在 eligible 时为 null，其他 decision 时等于 `decision_code`，用于向写工具和前端传递唯一业务错误。`eligibility_token` 仅在 `eligible` 时非空，绑定用户、会话、订单项、原因、规则版本和过期时间。模型不能生成有效令牌。

响应不变量：

```text
eligible                   = (decision == "eligible")
needs_clarification        = (decision == "needs_clarification")
needs_manual_review        = (decision == "needs_manual_review")
can_create_return_request  = eligible
handoff_required           = needs_manual_review
```

API、工具、SSE 和前端只能依据上述不变量渲染，不得出现 `decision=ineligible` 但 `eligible=true` 等冲突组合。

**权限与副作用**：仅当前用户本人订单；不写数据库。  
**错误码**：`ORDER_NOT_FOUND`、`INVALID_STATE`、`RETURN_NOT_ALLOWED`、`RETURN_WINDOW_EXPIRED`、`DUPLICATE_RETURN`、`MANUAL_REVIEW_REQUIRED`、`LOW_CONFIDENCE`、`UPSTREAM_UNAVAILABLE`。业务不符合时通过 `decision_code` 返回相同稳定码；鉴权、schema 和上游失败使用失败信封。  
**幂等**：只读；重复调用生成新的短期资格令牌，不改变业务数据。

### 5.9 `create_return_request`

**输入**

```json
{
  "order_id": "uuid",
  "order_item_id": "uuid",
  "reason_code": "SIZE_OR_FIT",
  "eligibility_token": "opaque-signed-token",
  "idempotency_key": "2d44d855-return-001"
}
```

`idempotency_key` 必须由 API `Idempotency-Key` 请求头或服务端逻辑操作 ID 注入，模型不能随意生成。工具还要求 `ToolContext.confirmation_state.verified=true`，且 `operation=create_return_request`、资源摘要与当前订单项一致；该状态只在用户明确确认后由服务端设置，不能由模型参数伪造。

直接 REST API 的 `confirmed=true` 由路由层验证当前认证用户后转换为一次性 `ConfirmationGrant`，再放入 `ToolContext`；Chat Agent 只能通过下一轮明确用户确认触发同样的服务端授权，不能输出或伪造 `confirmed`、`confirmation_state`。`eligibility_token` 必须声明 `decision=eligible`，否则写工具在事务内拒绝。

**输出 `data`**

```json
{
  "return_request_id": "uuid",
  "status": "submitted",
  "submitted_at": "2026-10-18T12:02:00Z",
  "review_required": true,
  "required_materials": ["商品及包装完好", "退货原因说明"],
  "next_action": "wait_for_review",
  "refund_status": "not_created",
  "notice": "申请已提交，但尚未退款；审核通过也不代表真实资金到账。"
}
```

**权限与副作用**：只能为当前用户本人订单创建；写 `return_requests`、`idempotency_records`、`tool_calls` 和 `audit_events`。只写 `submitted`，不创建真实退款。  
**错误码**：`ORDER_NOT_FOUND`、`CONFIRMATION_REQUIRED`、`ELIGIBILITY_EXPIRED`、`RETURN_NOT_ALLOWED`、`RETURN_WINDOW_EXPIRED`、`DUPLICATE_RETURN`、`MANUAL_REVIEW_REQUIRED`、`LOW_CONFIDENCE`、`IDEMPOTENCY_CONFLICT`、`IDEMPOTENCY_IN_PROGRESS`、`INVALID_STATE`、`UPSTREAM_UNAVAILABLE`。  
**幂等**：同一 `(shop_id, actor_user_id, operation, idempotency_key)` 和相同请求摘要只成功创建一次；重放返回同一资源、同一 `tool_call_id` 和 `idempotent_replay=true`，不新增工具调用记录。

### 5.10 `create_handoff_ticket`

**输入（调用者字段）**

```json
{
  "conversation_id": "uuid",
  "reason_code": "LEGAL_OR_REGULATORY",
  "summary_redacted": "用户要求投诉并提及法律途径；不得作出资金承诺。",
  "idempotency_key": "2d44d855-handoff-001"
}
```

`risk_level`、用户 ID、店铺 ID 和完整触发规则由服务端风险上下文注入，模型不能降级或覆盖；调用者字段 `reason_code` 也必须是规范风险规则码。`summary_redacted` 最多 500 字符，禁止完整 PII、系统 prompt 或密钥。

**输出 `data`**

```json
{
  "ticket_id": "uuid",
  "status": "open",
  "risk_level": "critical",
  "priority": 1,
  "queue": "priority_support",
  "primary_reason_code": "LEGAL_OR_REGULATORY",
  "reason_codes": ["LEGAL_OR_REGULATORY"],
  "expected_response": "客服将优先查看；这不是退款或赔偿承诺。",
  "created_at": "2026-10-18T12:03:00Z"
}
```

`primary_reason_code` 写入 `handoff_tickets.primary_reason_code`，完整 `reason_codes` 写入 `risk_rule_codes_jsonb`；返回数组与实际持久化内容一致。

**权限与副作用**：当前会话所有者或授权风险服务可触发；只能写 `open` 工单、幂等、工具调用和审计。高风险自动升级不要求用户确认；用户主动请求人工时，明确请求本身构成升级意图，但仍不要求 `confirmed` 参数。  
**错误码**：`CONVERSATION_NOT_FOUND`、`VALIDATION_ERROR`、`IDEMPOTENCY_CONFLICT`、`IDEMPOTENCY_IN_PROGRESS`。  
**幂等**：同一 `(shop_id, actor_user_id, operation, idempotency_key)` 和相同请求摘要只创建一条工单；重放返回同一资源、同一 `tool_call_id` 和 `idempotent_replay=true`。

## 6. 工具权限与副作用矩阵

| 工具 | shopper | support | admin | 副作用 |
|---|---|---|---|---|
| `search_products` | 本店 | 本店只读 | 本店只读 | 无 |
| `get_product_detail` | 本店 | 本店只读 | 本店只读 | 无 |
| `compare_products` | 本店 | 本店只读 | 本店只读 | 无 |
| `check_stock` | 本店 | 本店只读 | 本店只读 | 无 |
| `get_promotion` | 本店 | 本店只读 | 本店只读 | 无 |
| `get_order_status` | 本人订单 | 仅授权会话已绑定的目标用户，读脱敏摘要 | 不默认开放 | 无 |
| `get_shipment` | 本人订单 | 仅授权会话已绑定的目标用户，读脱敏摘要 | 不默认开放 | 无 |
| `check_return_eligibility` | 本人订单 | 仅授权会话，读/复核 | 只读授权摘要 | 无 |
| `create_return_request` | 本人、确认后 | 不得代消费者伪造确认 | 不得绕过审计 | 写申请 |
| `create_handoff_ticket` | 当前会话 | 可在授权范围内创建/跟进 | 授权工单范围内可见 | 写工单 |

客服工作台查看的是会话中已记录的脱敏工具摘要，不允许把任意 `target_user_id` 传入消费者工具来扩大查询范围。

## 7. 确定性业务规则

### 7.1 退货资格规则 `demo-return-v1`

规则按以下优先级执行，并返回所有命中的规则码：

| 优先级 | 输入/条件 | decision 与 decision_code | 可创建申请 | 创建工单 |
|---:|---|---|---:|---:|
| 0 | schema 非法、枚举非法或缺少必填实体 | 失败信封 `VALIDATION_ERROR` | 否 | 否 |
| 1 | 订单或订单项不存在、属于他人或跨店铺 | `ineligible / ORDER_NOT_FOUND` | 否 | 否 |
| 2 | 首次低置信度且无权益风险 | `needs_clarification / LOW_CONFIDENCE` | 否 | 否 |
| 3a | 首次澄清后仍低置信度 | `needs_manual_review / LOW_CONFIDENCE`，handoff 原因为 `LOW_CONFIDENCE` | 否 | 是 |
| 3b | 低置信度涉及用户权益 | `needs_manual_review / LOW_CONFIDENCE`，handoff 原因为 `LOW_CONFIDENCE` | 否 | 是 |
| 4 | 订单状态为 `created/paid/processing/shipped` | `ineligible / INVALID_STATE` | 否 | 否 |
| 5 | 订单状态为 `cancelled` | `ineligible / RETURN_NOT_ALLOWED` | 否 | 否 |
| 6 | 订单项不是 `active` | `ineligible / INVALID_STATE` | 否 | 否 |
| 7 | `is_returnable_snapshot=false` | `ineligible / RETURN_NOT_ALLOWED` | 否 | 否 |
| 8 | 同一订单项已有任一阻断申请（`submitted/under_review/approved/completed`） | `ineligible / DUPLICATE_RETURN` | 否 | 否 |
| 9 | 原因为损伤、错发、质量问题或其他 | `needs_manual_review / MANUAL_REVIEW_REQUIRED`，handoff 原因为 `RETURN_REASON_REQUIRES_REVIEW` | 否 | 是 |
| 10 | `delivered_at` 为空 | `ineligible / INVALID_STATE` | 否 | 否 |
| 11 | `now > delivered_at + 7 days` | `ineligible / RETURN_WINDOW_EXPIRED` | 否 | 否 |
| 12 | `line_total_cents >= 500000` | `needs_manual_review / MANUAL_REVIEW_REQUIRED`，handoff 原因为 `HIGH_VALUE_ORDER` | 否 | 是 |
| 13 | 其他条件均通过 | `eligible / RETURN_ELIGIBLE` | 是 | 否 |
| 14 | 首次上游工具失败 | 失败信封 `UPSTREAM_UNAVAILABLE` | 否 | 否 |
| 15 | 同一工具连续第二次失败 | `UPSTREAM_UNAVAILABLE`，handoff 原因为 `TOOL_FAILURE_REPEATED` | 否 | 是 |
| 16 | 创建申请时用户未确认 | 失败信封 `CONFIRMATION_REQUIRED` | 否 | 否 |
| 17 | 用户已确认、令牌有效且 decision=eligible | 创建成功，`status=submitted` | 已创建 | 否 |
| 18 | 用户已确认但 decision 不是 eligible | 对应 decision_code 作为错误码 | 否 | `decision=needs_manual_review` 时为是，否则否 |

1. **归属与订单项**：订单或订单项不存在、属于他人或跨店铺时，均返回 `decision=ineligible`、`decision_code=ORDER_NOT_FOUND`、`can_create_return_request=false`；不泄露资源存在性、不创建工单。
2. **订单状态**：`delivered/completed` 继续判断；`created/paid/processing/shipped` 返回 `decision=ineligible`、`decision_code=INVALID_STATE`；`cancelled` 返回 `decision=ineligible`、`decision_code=RETURN_NOT_ALLOWED`。三种结果都不允许创建申请。
3. **订单项状态**：仅 `active` 可继续；`cancelled/returned` 返回 `decision=ineligible`、`decision_code=INVALID_STATE`。
4. **可退类别**：`is_returnable_snapshot=false` 返回 `decision=ineligible`、`decision_code=RETURN_NOT_ALLOWED`。
5. **已有申请**：同一 `shop_id + order_item_id` 已存在 `submitted/under_review/approved` 的任一有效申请时，返回 `decision=ineligible`、`decision_code=DUPLICATE_RETURN` 和原申请摘要；不区分 `reason_code`，不创建第二条申请。
   - **已完成的退货申请同样阻断重复申请**：状态为 `completed` 的记录也计入阻断集合（`db/repositories/orders.py::_CLOSED_RETURN_STATUSES`）。原因是审批完成后本仓库没有任何代码把 `order_items.status` 改成 `returned`，若只看三个进行中状态，消费者可在同一订单项上再次提交相同申请。
   - `rejected`/`draft`/`cancelled` **不**阻断：被拒或未提交后，消费者仍可在期限内重新申请。
   - 数据库层 `uq_return_active_item` 部分唯一索引只覆盖 `submitted/under_review/approved`；`completed` 的阻断由仓库层查询保证，读写两条路径（`check_return_eligibility`、`create_return_request`）都经过该查询。
6. **低置信度**：路由意图或必要实体置信度低于 `0.70`，或原因不足以确定枚举时，不创建申请。首次返回 `decision=needs_clarification`、`decision_code=LOW_CONFIDENCE`、`handoff_required=false`。澄清后仍不足时，返回 `decision=needs_manual_review`、`decision_code=LOW_CONFIDENCE`、`handoff_required=true`；低置信度直接涉及权益时使用相同人工结果。
7. **原因分流**：
   - `SIZE_OR_FIT`、`NO_LONGER_NEEDED`：继续执行签收时间和金额规则。
   - `DAMAGED_ON_ARRIVAL`、`WRONG_ITEM`、`QUALITY_ISSUE`、`OTHER`：返回 `decision=needs_manual_review`、`decision_code=MANUAL_REVIEW_REQUIRED`、`can_create_return_request=false`、`handoff_required=true`，handoff 主原因使用 `RETURN_REASON_REQUIRES_REVIEW`。
8. **签收时间**：`delivered_at` 为空时返回 `decision=ineligible`、`decision_code=INVALID_STATE`。
9. **期限边界**：`deadline_at = order_items.delivered_at + interval '7 days'`；`now <= deadline_at` 继续，`now > deadline_at` 返回 `decision=ineligible`、`decision_code=RETURN_WINDOW_EXPIRED`。
10. **高风险金额**：`line_total_cents >= 500000` 时返回 `decision=needs_manual_review`、`decision_code=MANUAL_REVIEW_REQUIRED`、风险等级至少 `high`、`can_create_return_request=false`、`handoff_required=true`，handoff 主原因使用 `HIGH_VALUE_ORDER`。
11. **可申请条件**：仅当 `decision=eligible` 且资格令牌未过期时，才允许调用 `create_return_request`。
12. **用户确认**：`check_return_eligibility` 只读且不要求确认；创建申请前必须由服务端确认状态证明用户已明确确认。资格令牌 10 分钟过期；订单、商品、签收时间或已有申请变化时重新检查。

工具失败规则：第一次受控上游失败返回 `UPSTREAM_UNAVAILABLE`，不写库且允许一次重试；同一会话同一工具连续第二次失败后停止重试、返回相同错误并强制 `handoff_required=true`。低置信度、工具失败和 `needs_manual_review` 均不得调用写工具。

必须覆盖的边界测试：订单不存在/他人/跨店铺、全部订单状态、未签收、不可退类别、已有任一有效申请（含 `completed` 阻断与 `rejected`/`draft` 不阻断）、全部 `reason_code`、低置信度首次/重复、工具失败首次/连续第二次、截止时刻前 1 秒/截止时刻/后 1 秒、499999/500000/500001 分、未确认/已确认、重复幂等请求。

### 7.2 退款边界

1. `create_return_request` 只创建申请，不创建退款案例。
2. `refund_cases` 只能由确定性规则或授权 `support/admin` 流程推进；LLM 和聊天工具没有写权限。
3. 退款金额必须为非负整数分、币种一致且不超过对应订单项金额；MVP 只允许 mock/synthetic 状态。
4. `approved_synthetic` 不等于退款到账；输出必须明确说明。
5. 用户要求立即退款、赔付、免单、优惠券或改价时，系统只能解释规则、查询已有状态、创建申请或转人工；不得输出保证性承诺。
6. 当前 10 个工具和公开 API 不提供退款审批或人工审核写接口；`refund_cases` 的人工流程字段只保留给后续单独评审，阶段 6–12 不得用 prompt 临时扩展该权限。

### 7.3 转人工风险规则

以下规则任一命中即应进入人工路径，风险级别取命中规则中的最高级别：

| 规则码 | 条件 | 最低风险 |
|---|---|---|
| `USER_REQUESTS_HUMAN` | 用户明确要求人工/真人/客服接管 | high |
| `COMPLAINT` | 投诉、强烈不满并要求追责 | high |
| `LEGAL_OR_REGULATORY` | 起诉、律师、监管、曝光等 | critical |
| `PERSONAL_SAFETY` | 人身安全、威胁或紧急危险 | critical |
| `PRIVACY_OR_ACCOUNT_TAKEOVER` | 隐私泄露、账号被盗、疑似欺诈 | critical |
| `MONEY_DECISION_REQUIRED` | 要求直接退款、赔偿、免单、发券或改价 | high |
| `HIGH_VALUE_ORDER` | 订单项总金额 >= 500000 分 | high |
| `RETURN_REASON_REQUIRES_REVIEW` | 损伤、错发、质量问题或其他退货原因 | high |
| `POLICY_CONFLICT` | 两个当前有效片段给出冲突规则 | high |
| `INSUFFICIENT_EVIDENCE_RIGHTS` | 政策证据不足且影响用户权益 | high |
| `TOOL_FAILURE_REPEATED` | 同一工具连续失败 2 次 | high |
| `TOOL_MODEL_CONFLICT` | 模型声称与工具事实冲突 | high |
| `OUTPUT_GUARD_MONEY` | 输出出现未经授权的资金承诺 | high |
| `OUTPUT_GUARD_PII` | 输出准备包含完整 PII | high |
| `ABNORMAL_ORDER_PATTERN` | 订单频率/金额/地址异常规则命中 | medium/high |
| `LOW_CONFIDENCE` | 意图或证据不足 | medium；涉及权益时 high |

风险码选择规则：

1. `risk_level` 取所有命中规则中的最高等级。
2. `primary_reason_code` 取最高等级规则中在本表中最早出现的一项。
3. `risk_rule_codes_jsonb` 保存全部命中规则，且必须包含 `primary_reason_code`。
4. 工单优先级固定为 `critical=1`、`high=2`、`medium=3`、`low=4`；`5` 保留给人工调高优先级。

执行要求：

1. 高风险不继续生成安抚式资金承诺。
2. 同一会话/原因/idempotency key 只创建一个工单。
3. 工单摘要只包含客服处理所需的最小信息，不含完整 PII。
4. 低置信度先澄清；一旦涉及权益或无法澄清，必须转人工。
5. 输出护栏发现资金/PII 问题时优先阻断输出并升级，不以“已修正”掩盖原冲突。

## 8. 幂等规则

适用于 `create_return_request` 和 `create_handoff_ticket`；未来写工具必须先更新本契约和测试。

1. 作用域：`(shop_id, actor_user_id, operation, idempotency_key)`；`actor_user_id` 是实际发起写入的人，不是被查询的目标用户。
2. key 长度 16-128，字符集 `[A-Za-z0-9._:-]`；不包含 PII。
3. 服务端对规范化业务参数计算 `request_hash`。相同 key、相同 hash：
   - 已成功：返回原资源与 `idempotent_replay=true`。
   - 处理中：返回 `IDEMPOTENCY_IN_PROGRESS`，可短间隔重试。
   - 已失败且不可重试：返回原安全失败；可重试错误按工具契约处理。
4. 相同 key、不同 hash：`IDEMPOTENCY_CONFLICT`，不覆盖原记录。
5. 数据库唯一约束是最终仲裁；并发请求只能有一个创建资源。
6. 幂等记录至少保留 7 天；退货申请和工单的业务去重约束保留更久，避免过期重试产生重复。
7. 审计记录包含 key 的哈希/摘要、操作者、会话、工具、请求摘要、结果、request ID 和 trace ID，不记录完整 PII。
8. 幂等重放复用原业务资源和原 `tool_call_id`，不新增 `tool_calls` 行；另写一条 `idempotent_replay` 审计事件。`tool_calls` 唯一索引 `(shop_id, actor_user_id, tool_name, idempotency_key)` 是最终仲裁。

## 9. 工具调用预算与审计

- 单轮总工具调用最多 4 次。
- 同一工具连续失败 2 次后停止。
- 工具结果只向模型提供最小化字段；完整数据库记录不进入模型上下文。
- `tool_calls` 记录目标 `user_id`、操作者 `actor_user_id`、开始/结束、错误码、耗时和脱敏输入/结果摘要。
- 权限拒绝、幂等冲突、风险升级和输出冲突均写 `audit_events`。
- 任何异常必须映射为稳定错误码；不得把堆栈或数据库错误交给模型自由解释。

## 10. 验收要求

1. 10 个工具的 schema 都有未知字段拒绝、范围边界和输出 fixture 测试。
2. 订单/物流跨用户和跨店铺测试返回统一安全错误。
3. 退货窗口边界、原因分流、可退类别、风险和金额阈值有单元测试。
4. 创建退货/工单的并发同 key 测试只产生一条记录；不同 hash 返回冲突。
5. 模型不能通过参数改变 `shop_id/user_id/risk_level/confirmation_state`。
6. 高风险、低置信度和工具失败路径不会调用资金或未经确认的写工具。
7. 本文件中的规则在阶段 9 实现后，测试报告必须提供命令、用例数和输出证据。
