# ShopMate API 契约

> 阶段：阶段 3 — 架构、数据契约、工具契约与 API 契约  
> 版本：v1.0  
> 日期：2026-10-18  
> 状态：逻辑 API 契约；OpenAPI 与实现将在后续阶段验证  
> 业务前缀：`/api/v1`

## 1. 通用约定

1. JSON 字段使用 `snake_case`；时间为 ISO 8601 UTC，例如 `2026-10-18T12:00:00Z`。
2. 金额只使用整数 `*_cents` 加 `currency`；API 不接受浮点金额。
3. ID 为 UUID；分页使用不可见游标，默认 `limit=20`，最大 `100`。
4. 所有业务接口除注册、登录、验证码、健康检查和无敏感信息的系统元数据外都需要认证。
5. `shop_id`、`user_id`、角色和客服授权范围从认证上下文取得；请求体中出现身份字段时拒绝或忽略，不能用于授权。
6. 日志和错误响应不含完整手机号、地址、身份证、银行卡、token、SQL、堆栈或内部 URL。
7. 状态改变接口必须发送允许的 `Origin`；cookie 认证请求使用 CSRF token。
8. 写接口使用 `Idempotency-Key`；聊天使用 `client_message_id` 防止重复用户消息。

## 2. 认证、Token 与请求头

- Access token：短时 JWT，建议默认 15 分钟；前端只保存在内存，不写 URL 或 localStorage。
- Refresh token：默认 7 天，放在 `HttpOnly; Secure; SameSite=Lax` cookie；服务端只存哈希。
- `/auth/refresh` 强制 CSRF token；刷新时轮换 refresh token 并检测重放。
- `Authorization: Bearer <access_token>` 用于业务请求。
- `X-CSRF-Token` 用于 cookie 认证的状态改变请求。
- `Idempotency-Key` 用于退货申请和人工工单创建，格式见工具契约第 8 节。
- `X-Request-ID` 可选；服务端仍生成/规范化 `request_id` 和 `trace_id`。
- CORS 只允许显式 allowlist，不使用 `*` 配合 credentials。

## 3. 响应信封

### 3.1 成功

```json
{
  "data": {},
  "request_id": "5bfb04fe-ce23-4fc7-b3a6-7852ab6d0c6a",
  "trace_id": "a64f42b3-c26a-47a7-a57a-f1e0133416b0"
}
```

### 3.2 列表

```json
{
  "data": {
    "items": [],
    "next_cursor": null
  },
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

### 3.3 失败

```json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "未找到可由当前账号访问的订单。请核对订单号，或转人工协助。",
    "retryable": false,
    "retry_after_ms": null,
    "details": {}
  },
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

`details` 只允许安全字段级错误，例如 `field`、`reason`；生产响应不返回堆栈或内部查询。

HTTP 映射：

| 场景 | HTTP |
|---|---:|
| 成功读取/更新 | 200 |
| 创建资源 | 201 |
| 异步任务接受 | 202 |
| 请求 schema 错误 | 400 |
| 未认证 | 401 |
| 角色或权限拒绝 | 403 |
| 资源不存在或不可见 | 404 |
| 状态冲突/幂等冲突 | 409 |
| 请求过大/不支持类型 | 413/415 |
| 限流 | 429 |
| 上游或依赖不可用 | 503 |
| 未分类内部错误 | 500 |

订单、物流、退货和会话的“不存在”和“属于他人”对外使用同一状态/码，避免资源枚举。

## 4. 健康检查

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| GET | `/health` | 无 | 进程存活，不依赖外部服务 |
| GET | `/ready` | 无 | 检查 PostgreSQL、Redis、Milvus/Mock OMS 可用性 |
| GET | `/api/v1/system/meta` | 无 | 返回环境和 synthetic/mock 标识，不返回密钥或内部地址 |

`/health` 成功：

```json
{"status": "ok"}
```

`/ready` 成功：

```json
{
  "status": "ready",
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "milvus": "ok",
    "mock_oms": "ok"
  },
  "as_of": "2026-10-18T12:00:00Z"
}
```

失败只返回组件状态和稳定错误码，不返回连接串或堆栈。

`/api/v1/system/meta` 示例：

```json
{
  "data": {
    "environment": "demo",
    "data_classification": "synthetic",
    "is_synthetic": true,
    "notice": "当前展示合成演示数据，不代表真实经营数据。"
  },
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

阶段 11 必须使用该响应显示 Synthetic 横幅；商品卡片、订单和其他事实仍保留各自 `is_synthetic` 字段用于资源级校验。

## 5. 认证 API

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/api/v1/auth/register` | `email`, `password`, `captcha_token`, `captcha_answer` | 201，用户摘要 |
| POST | `/api/v1/auth/login` | `email`, `password`, `captcha_token`, `captcha_answer` | access token + refresh cookie |
| GET | `/api/v1/auth/captcha` | 无 | 验证码挑战和短期 `captcha_token` |
| POST | `/api/v1/auth/refresh` | 空 body；依赖 refresh cookie + CSRF | 轮换后的 access/refresh |
| POST | `/api/v1/auth/logout` | 空 body；CSRF | 撤销 refresh session |
| GET | `/api/v1/auth/me` | Bearer | 用户 ID、脱敏显示名、role、shop |

`login` 响应中的用户摘要不包含密码哈希、refresh token 明文或内部权限细节。

## 6. 会话与聊天 API

### 6.1 会话

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/conversations` | 当前用户未删除会话，游标分页 |
| POST | `/api/v1/conversations` | 创建会话，body `{title?}` |
| PATCH | `/api/v1/conversations/{id}` | 重命名，body `{title}` |
| DELETE | `/api/v1/conversations/{id}` | 软删除 |
| GET | `/api/v1/conversations/{id}/messages` | 当前用户会话历史 |

所有操作先校验 `shop_id + user_id + conversation_id`。消息列表支持 `before` 游标和最多 100 条；读取历史不重新发送旧 SSE。

### 6.2 聊天流式请求

```http
POST /api/v1/chat/stream HTTP/1.1
Accept: text/event-stream
Content-Type: application/json
Authorization: Bearer <access_token>
X-CSRF-Token: <token>
```

```json
{
  "conversation_id": "5a11d2b2-79a7-4b62-aa7d-b4f35ecebb9a",
  "message": "预算 300 元以内，适合通勤的降噪耳机",
  "client_message_id": "ea16e7d5-2fc9-4e48-a528-b5eac9d3f10c"
}
```

约束：`message` 1-4000 字符；`client_message_id` 为 UUID；会话必须在当前用户和店铺内。

`client_message_id` 幂等：

- 首次请求创建用户消息并开始流。
- 同一会话同一 ID 正在处理：返回 JSON `409 REQUEST_IN_PROGRESS`，不建立第二条流。
- 已成功/已完成：返回 JSON `409 DUPLICATE_REQUEST` 和原 `request_id`；客户端读取历史，不重复写入。
- 本 MVP 不支持 SSE 断点续传；`Last-Event-ID` 不触发历史流重放。

## 7. SSE 协议

### 7.1 传输格式

成功建立聊天流后返回：

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

每条事件：

```text
id: 1
event: meta
data: {"schema_version":"1.0","event_id":"1","request_id":"uuid","sequence":1,"occurred_at":"2026-10-18T12:00:00Z","type":"meta","data":{}}

```

`event:` 必须与 payload 的 `type` 一致；`data:` 必须是单行 JSON。业务事件只允许：

```text
meta
tool_status
product_card
citation
delta
done
error
```

保活使用 SSE 注释行 `: keepalive`，每 15 秒最多一次，不作为业务事件。`sequence` 从 1 递增；同一流内唯一。

### 7.2 公共事件 envelope

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 当前 `1.0` |
| `event_id` | string | 与 SSE `id` 一致 |
| `request_id` | UUID | 本轮请求 |
| `sequence` | integer | 从 1 单调递增 |
| `occurred_at` | string | UTC ISO 8601 |
| `type` | enum | 七种事件之一 |
| `data` | object | 事件专属 payload |

### 7.3 `meta`

必须首个发送且只发送一次。

```json
{
  "schema_version": "1.0",
  "event_id": "1",
  "request_id": "uuid",
  "sequence": 1,
  "occurred_at": "2026-10-18T12:00:00Z",
  "type": "meta",
  "data": {
    "trace_id": "uuid",
    "conversation_id": "uuid",
    "user_message_id": "uuid",
    "route": "product_discovery",
    "data_classification": "synthetic",
    "is_synthetic": true,
    "stream_version": "1.0"
  }
}
```

`route` 使用架构文档的 10 类意图。流建立前若认证或会话失败，返回普通 JSON HTTP 错误，不建立 SSE。

### 7.4 `tool_status`

可在工具开始/结束/失败时多次发送；不把工具内部异常原文传给前端。

```json
{
  "schema_version": "1.0",
  "event_id": "2",
  "request_id": "uuid",
  "sequence": 2,
  "occurred_at": "2026-10-18T12:00:01Z",
  "type": "tool_status",
  "data": {
    "tool_call_id": "uuid",
    "tool_name": "get_order_status",
    "status": "started",
    "display_message": "正在查询订单状态",
    "latency_ms": null,
    "error_code": null
  }
}
```

`status`：`started/succeeded/failed/skipped`；`display_message` 为受控中文文案。

### 7.5 `product_card`

每个可展示商品发送一次；价格、库存和 `as_of` 必须来自工具事实。

```json
{
  "schema_version": "1.0",
  "event_id": "3",
  "request_id": "uuid",
  "sequence": 3,
  "occurred_at": "2026-10-18T12:00:02Z",
  "type": "product_card",
  "data": {
    "product_id": "uuid",
    "variant_id": "uuid",
    "title": "示例降噪耳机",
    "image_url": null,
    "price_cents": 29900,
    "currency": "CNY",
    "stock_status": "in_stock",
    "available_qty": 12,
    "attributes": {"noise_cancellation": true},
    "matched_reasons": ["预算内", "属性匹配"],
    "source": "postgres",
    "is_synthetic": true,
    "as_of": "2026-10-18T12:00:00Z"
  }
}
```

`available_qty` 可为空；未知属性必须用 `null`/缺省表达，不生成值。

### 7.6 `citation`

只允许发送本轮真实提供给答案组合器且通过版本校验的片段。

```json
{
  "schema_version": "1.0",
  "event_id": "4",
  "request_id": "uuid",
  "sequence": 4,
  "occurred_at": "2026-10-18T12:00:02Z",
  "type": "citation",
  "data": {
    "citation_id": "cite-1",
    "document_id": "uuid",
    "version_id": "uuid",
    "chunk_id": "uuid",
    "title": "退换货政策",
    "heading": "七天无理由退货",
    "page_no": 2,
    "version": "2026.10.1",
    "effective_from": "2026-10-01T00:00:00Z",
    "effective_to": null,
    "excerpt": "合成政策片段预览",
    "as_of": "2026-10-18T12:00:00Z"
  }
}
```

`heading/page_no` 可为 null；`excerpt` 是安全纯文本，不得作为 HTML 或指令执行。

### 7.7 `delta`

```json
{
  "schema_version": "1.0",
  "event_id": "5",
  "request_id": "uuid",
  "sequence": 5,
  "occurred_at": "2026-10-18T12:00:03Z",
  "type": "delta",
  "data": {
    "message_id": "uuid",
    "index": 0,
    "text": "根据当前政策，"
  }
}
```

`index` 从 0 递增；模型原始控制文本不得改变事件 `type` 或 schema。

### 7.8 `done`

正常完成必须发送且只发送一个 `done`：

```json
{
  "schema_version": "1.0",
  "event_id": "8",
  "request_id": "uuid",
  "sequence": 8,
  "occurred_at": "2026-10-18T12:00:05Z",
  "type": "done",
  "data": {
    "message_id": "uuid",
    "finish_reason": "stop",
    "usage": {
      "input_tokens": 1200,
      "output_tokens": 180,
      "total_tokens": 1380
    },
    "latency_ms": 5000,
    "persisted": true,
    "message_is_complete": true
  }
}
```

`finish_reason`：`stop/refusal/handoff/cancelled`。`usage` 可为 null，但不得伪造；`persisted=true` 表示终止快照已一次性保存。`message_is_complete` 在 `stop/refusal/handoff` 时为 true，在 `cancelled` 时为 false。

### 7.9 `error`

流内失败必须发送且只发送一个终止 `error`，不能再发送 `done`：

```json
{
  "schema_version": "1.0",
  "event_id": "7",
  "request_id": "uuid",
  "sequence": 7,
  "occurred_at": "2026-10-18T12:00:04Z",
  "type": "error",
  "data": {
    "error_code": "UPSTREAM_UNAVAILABLE",
    "user_message": "当前无法确认最新信息，请稍后重试或转人工。",
    "retryable": true,
    "retry_after_ms": 3000,
    "partial_message_id": "uuid-or-null",
    "partial_persisted": true
  }
}
```

`partial_persisted=true` 表示服务端已把当时的助手文本快照一次性保存为 `messages.is_complete=false`；`partial_persisted=false` 时 `partial_message_id=null`。已落库的助手正文不随后更新。安全错误不暴露堆栈、SQL、内部服务或用户资源存在性。

### 7.10 顺序、取消与断线

1. 第一个业务事件必须是 `meta`。
2. `product_card` 和 `citation` 可在 `delta` 前后发送，但必须已通过事实/版本校验。
3. 终止事件只能是最后一个业务事件：一个 `done` 或一个 `error`。
4. 客户端 abort 连接时，服务端尽快停止 LLM/工具调用；若仍可写，先一次性保存取消快照并发送 `done(finish_reason=cancelled)`。若连接已不可写，仍尽量保存一份 `is_complete=false` 的助手快照供历史读取；无法保存时不虚构 `partial_message_id`。
5. 服务端总流超时建议 120 秒，首事件应在 2 秒内开始，空闲 30 秒发保活；具体配置计入 `.env.example`。
6. MVP 不做多条流复用、恢复和 Last-Event-ID 重放。断线后前端重新读取消息历史，显示未完成状态，再由用户决定是否重试。
7. 同一 `client_message_id` 的重试按第 6.2 节处理，不重复写用户消息。

## 8. 商品 API

| 方法 | 路径 | 请求要点 | 响应 |
|---|---|---|---|
| GET | `/api/v1/products/search` | `q`, `category`, `brand`, `budget_min_cents`, `budget_max_cents`, `in_stock_only`, `limit`, `cursor` | 商品卡片与 `as_of` |
| GET | `/api/v1/products/{id}` | 可选 `variant_id` | 商品、SKU、真实价格、库存摘要 |
| POST | `/api/v1/products/compare` | `product_ids` 2-4，`attributes?` | 对齐比较表，缺失 `unknown` |

`budget_max_cents=30000` 表示 300 元；边界金额按包含规则。所有响应事实来自结构化数据，前端不得根据描述推断价格或库存；商品卡片和详情包含 `is_synthetic`。

## 9. 订单与物流 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/orders` | 当前用户订单列表；可按状态、时间过滤 |
| GET | `/api/v1/orders/{id}` | 当前用户订单详情，校验归属 |
| GET | `/api/v1/orders/{id}/shipment` | 当前用户物流，返回脱敏单号、节点、更新时间 |

订单详情响应示例：

```json
{
  "data": {
    "id": "uuid",
    "order_no": "DEMO-1001",
    "status": "shipped",
    "total_cents": 29900,
    "currency": "CNY",
    "is_synthetic": true,
    "placed_at": "2026-10-15T02:00:00Z",
    "status_updated_at": "2026-10-17T01:00:00Z",
    "items": [
      {
        "id": "uuid",
        "sku": "DEMO-HEAD-001",
        "title": "示例降噪耳机",
        "quantity": 1,
        "unit_price_cents": 29900,
        "status": "active"
      }
    ]
  },
  "request_id": "uuid",
  "trace_id": "uuid"
}
```

订单与物流响应包含 `is_synthetic`。物流只返回 `tracking_no_masked`，不返回完整地址、完整收件人或完整手机号。查询订单/物流的 Repository 必须同时使用 `shop_id` 与 `effective_user_id`。

## 10. 退货 API

### 10.1 检查资格

```http
POST /api/v1/returns/eligibility
```

```json
{
  "order_id": "uuid",
  "order_item_id": "uuid",
  "reason_code": "SIZE_OR_FIT"
}
```

返回字段固定为：

| 字段 | 类型 | 说明 |
|---|---|---|
| `decision` | enum | `eligible/ineligible/needs_clarification/needs_manual_review` |
| `decision_code` | string | 稳定业务结果码，如 `RETURN_ELIGIBLE`、`INVALID_STATE`、`MANUAL_REVIEW_REQUIRED` |
| `error_code` | string/null | eligible 为 null；其他 decision 等于 `decision_code` |
| `eligible` | boolean | `decision == "eligible"` |
| `needs_clarification` | boolean | `decision == "needs_clarification"` |
| `needs_manual_review` | boolean | `decision == "needs_manual_review"` |
| `can_create_return_request` | boolean | 仅 `eligible=true` 时为 true |
| `handoff_required` | boolean | `needs_manual_review=true` 时为 true，编排器必须调用 handoff 工具 |
| `matched_rule_codes` | string[] | 命中的规则码 |
| `deadline_at` | timestamp/null | 已签收可退原因使用 7 天窗口时返回 |
| `required_materials` | string[] | 用户后续需要准备的材料 |
| `next_action` | string | `confirm_to_submit/clarify/contact_support/wait` |
| `eligibility_token` | string/null | 仅 decision=eligible 时签发，10 分钟过期 |
| `eligibility_expires_at` | timestamp/null | 与 token 同时出现 |
| `rule_version` | string | 当前为 `demo-return-v1` |
| `evaluated_at` | UTC timestamp | 规则计算时间 |

该接口是只读规则检查，不创建申请或工单；`handoff_required=true` 时由 chat orchestration 调用 `create_handoff_ticket`。所有布尔字段必须满足工具契约第 5.8 节的不变量。

### 10.2 创建申请

```http
POST /api/v1/returns
Idempotency-Key: 2d44d855-return-001
```

```json
{
  "order_id": "uuid",
  "order_item_id": "uuid",
  "reason_code": "SIZE_OR_FIT",
  "eligibility_token": "opaque-signed-token",
  "confirmed": true
}
```

约束：

1. `confirmed=true` 必须来自用户明确操作。REST 路由将其转换为绑定 actor、effective user、operation、资源摘要和过期时间的一次性 `ConfirmationGrant`，再交给工具层；Chat Agent 不能自行设置该字段或 `confirmation_state`。
2. `eligibility_token` 仅在 `decision=eligible` 时签发，绑定当前用户、会话、订单项、原因、规则版本和过期时间。
3. 服务端在同一事务内重新验证订单/订单项归属、状态、窗口、已有申请和幂等键。
4. 成功返回 201，状态只能是 `submitted`；`refund_status` 为 `not_created`。未确认返回 `409 CONFIRMATION_REQUIRED`；`needs_manual_review`、`needs_clarification` 和 `ineligible` 令牌不能用于创建申请。
5. 相同幂等键重放返回 200 或等价成功结构，并标记 `idempotent_replay=true`；不同摘要返回 409 `IDEMPOTENCY_CONFLICT`。

## 11. 人工工单 API

消费者接口仅允许访问当前用户自己的工单：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/handoff` | 当前用户工单列表，按创建时间倒序 |
| GET | `/api/v1/handoff/{id}` | 当前用户工单详情 |

列表项和详情只返回 `ticket_id`、`status`、`risk_level`、`primary_reason_code`、`reason_codes`、`created_at`、`updated_at`、`expected_response` 和脱敏安全摘要；不返回内部队列、其他用户字段或系统 prompt。

创建工单：

```http
POST /api/v1/handoff
Idempotency-Key: 2d44d855-handoff-001
```

```json
{
  "conversation_id": "uuid",
  "reason_code": "LEGAL_OR_REGULATORY",
  "summary_redacted": "用户要求投诉并提及法律途径；不得作出资金承诺。"
}
```

`reason_code` 必须使用工具契约第 7.3 节的规范风险码。服务端从风险上下文注入 `risk_level`、全部 `reason_codes`、主原因、用户和店铺范围。高风险自动升级不要求 `confirmed`；用户主动请求人工时，明确请求本身构成升级意图。

成功返回 `ticket_id`、`status=open`、`primary_reason_code`、`reason_codes`、`queue`、`priority` 和安全说明；数据库同时保存 `primary_reason_code` 与 `risk_rule_codes_jsonb`。不得返回其他店铺队列或完整对话。

## 12. 客服工作台 API

> **实现现状（阶段 14 核对，2026-10-20）**：本章为**契约**。截至阶段 14，`/api/v1/support/*` **尚未在
> 应用中注册**（`src/.../main.py` 未 include 该路由），实际请求返回 404。前端客服工作台页面因此显示错误态；
> 消费者侧可用 `GET /api/v1/handoff` 查看自己的工单，工单数据已正常入库。
> 实现本章端点前，不得在演示或文档中宣称客服工作台可用。

仅 `support` 或具备客服权限的 `admin`，且只能访问授权店铺和授权工单关联资源：

- 工单列表/详情要求 `support:ticket:read`；support 角色默认具备，admin 需要显式授予。
- 工单接管/解决/关闭要求 `support:ticket:write`；support 角色默认具备，admin 需要显式授予。
- 查看工单关联会话要求 `support:conversation:read`；admin 默认不具备。
- 回答质量标记要求 `support:quality_label:write`；仍须同时通过目标消息归属校验。

support 查看会话必须由授权工单提供业务理由；admin 默认不浏览用户会话。任何角色都不得列出或搜索全部消费者会话。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/support/tickets` | 风险/等待时间排序的工单队列 |
| GET | `/api/v1/support/tickets/{id}` | 工单、会话/退货安全摘要、引用、工具摘要和风险 |
| PATCH | `/api/v1/support/tickets/{id}` | 接管、解决、关闭；状态转换审计 |
| GET | `/api/v1/support/conversations/{id}` | 授权会话及消息/引用摘要 |
| POST | `/api/v1/support/messages/{assistant_message_id}/quality-labels` | 写 `correct/incorrect/needs_knowledge` |

`GET /api/v1/support/tickets` 列表项固定字段：

```json
{
  "ticket_id": "uuid",
  "status": "open",
  "risk_level": "high",
  "primary_reason_code": "COMPLAINT",
  "reason_codes": ["COMPLAINT", "MONEY_DECISION_REQUIRED"],
  "priority": 2,
  "queue": "priority_support",
  "conversation_id": "uuid",
  "user_reference_masked": "user-****01",
  "assigned_to_masked": null,
  "created_at": "2026-10-18T12:00:00Z",
  "waiting_seconds": 120
}
```

`PATCH /api/v1/support/tickets/{id}` 请求：

```json
{
  "action": "assign",
  "assignee_user_id": "uuid",
  "resolution_summary": null,
  "close_reason": null
}
```

`assignee_user_id` 为可选 UUID；缺省或 `null` 表示当前客服自接管。`resolution_summary` 仅 `resolve` 时必填，`close_reason` 仅 `close` 时可选；与 action 不匹配的字段必须为 null 或省略。

合法状态转换固定为：

| action | 允许原状态 | 新状态 | 额外要求 |
|---|---|---|---|
| `assign` | `open/assigned` | `assigned` | assignee 必须是同店 support/admin |
| `resolve` | `assigned` | `resolved` | `resolution_summary` 1-500 字符 |
| `close` | `resolved` | `closed` | `close_reason` 可选安全摘要 |

响应返回 `ticket_id`、`status`、`assigned_to_masked`、`updated_at` 和审计 `request_id`。非法转换返回 `409 INVALID_STATE`。

`GET /api/v1/support/conversations/{id}` 返回：

```json
{
  "conversation_id": "uuid",
  "title": "订单售后咨询",
  "owner_reference_masked": "user-****01",
  "target_user_id": "uuid",
  "ticket_id": "uuid",
  "messages": [
    {
      "message_id": "uuid",
      "role": "assistant",
      "content": "安全展示内容",
      "is_complete": true,
      "citations": [],
      "risk": {"level": "high", "rule_codes": ["COMPLAINT"]},
      "created_at": "2026-10-18T12:00:00Z"
    }
  ],
  "tool_calls": [
    {
      "tool_call_id": "uuid",
      "tool_name": "get_order_status",
      "status": "succeeded",
      "latency_ms": 120,
      "result_summary": {"status": "shipped"}
    }
  ],
  "handoff": {
    "ticket_id": "uuid",
    "status": "open",
    "primary_reason_code": "COMPLAINT"
  }
}
```

`target_user_id` 来自授权工单关联会话，不接受查询参数指定；响应不得包含完整 PII、系统 prompt、密钥或内部堆栈。

质量标记 body：

```json
{
  "label": "needs_knowledge",
  "reason_summary": "现有片段未覆盖配送地区"
}
```

标记只进入审核/评测流程，不直接修改当前知识版本、检索结果或模型参数。普通用户和跨店铺请求必须被拒绝。

## 13. 管理端 API

> **实现现状（阶段 14 核对，2026-10-20）**：以下接口中**已实现**的是
> `GET/POST /admin/knowledge-bases`、`GET /admin/documents`、`GET /admin/documents/{id}`、
> `GET /admin/chunks`、`GET /admin/eval/runs`、`POST /admin/eval/run`、`GET /admin/model-profiles`。
> **未实现**：`POST /admin/documents`（上传）、`PATCH/DELETE /admin/chunks/{id}`、`POST /admin/documents/{id}/reindex`。
> 知识入库当前通过 `scripts/ingest.py` 与 `scripts/rebuild_knowledge_index.py` 完成；
> 前端上传/编辑按钮在未实现前会失败，这属于已知缺口（见 `README.md` §9、`docs/08-deployment.md` §12）。

所有接口要求 `admin` 和当前店铺范围。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/knowledge-bases` | 知识库列表 |
| POST | `/api/v1/admin/knowledge-bases` | 创建知识库 |
| POST | `/api/v1/admin/documents` | `multipart/form-data` 上传并创建新版本 |
| GET | `/api/v1/admin/documents` | 文档/解析状态列表 |
| GET | `/api/v1/admin/documents/{id}` | 文档、版本和解析状态 |
| GET | `/api/v1/admin/chunks` | 片段预览/筛选 |
| PATCH | `/api/v1/admin/chunks/{id}` | 编辑指定版本片段 |
| DELETE | `/api/v1/admin/chunks/{id}` | 停用/软删除片段 |
| POST | `/api/v1/admin/documents/{id}/reindex` | 创建新 ingestion job |
| GET | `/api/v1/admin/eval/runs` | 评测历史 |
| POST | `/api/v1/admin/eval/run` | 受控触发评测 |
| GET | `/api/v1/admin/model-profiles` | 返回安全 profile 元数据，不返回密钥 |

上传约束：MVP 仅接受 PDF、DOCX、PPTX、Markdown、TXT；单请求一个文件，最大 20 MiB；服务端校验扩展名、实际 MIME/魔数、页数/解压后大小、文件名重命名和受控目录。解析失败状态为 `failed`，并保留安全错误原因。具体并发和超时在配置中固定并测试。

片段编辑/停用后必须使相关缓存失效；旧版本保留，不能覆盖历史版本。评测运行返回 202 和 `eval_run_id`，结果通过列表接口读取。

`POST /api/v1/admin/documents` 的 `multipart/form-data` 字段：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `knowledge_base_id` | 是 | 当前店铺知识库 |
| `title` | 是 | 1-240 字符 |
| `doc_type` | 是 | `policy/faq/manual/warranty/invoice/shipping/other` |
| `locale` | 是 | BCP 47，如 `zh-CN` |
| `region` | 是 | ISO 3166-1 alpha-2 |
| `effective_from` | 是 | UTC ISO 8601 |
| `effective_to` | 否 | UTC ISO 8601，必须晚于 from |
| `file` | 是 | 单个受支持文件，最大 20 MiB |

成功返回 202：

```json
{
  "document_id": "uuid",
  "version_id": "uuid",
  "ingestion_job_id": "uuid",
  "parse_status": "pending"
}
```

发现的不安全文件名、路径穿越、符号链接、可执行内容、伪造 MIME 或超限文件整单拒绝，不创建 ready 版本。

`GET /api/v1/admin/documents` 列表项字段：`document_id`、`title`、`doc_type`、`knowledge_base_id`、`status`、`locale`、`region`、`current_version_id`、`current_version`、`parse_status`、`effective_from`、`effective_to`、`updated_at`、`is_synthetic`。

`GET /api/v1/admin/chunks` 列表项字段：`chunk_id`、`document_id`、`version_id`、`chunk_index`、`heading_path`、`page_no`、`text`、`token_count`、`is_enabled`、`updated_at`。

`PATCH /api/v1/admin/chunks/{id}` 请求至少包含一个修改字段：

```json
{
  "text": "修正后的知识单元文本",
  "is_enabled": true,
  "change_reason": "修正章节措辞"
}
```

成功响应返回 `chunk_id`、`version_id`、`text`、`is_enabled`、`content_hash`、`reindex_required=true`、`updated_at`。文本修改必须重算 hash、失效相关缓存，并在 Milvus 重建完成前保持可追踪的索引状态；不能静默覆盖历史文本。

`POST /api/v1/admin/eval/run` 请求：

```json
{
  "dataset_name": "shopmate-core",
  "dataset_version": "v1",
  "config_profile_id": "uuid-or-null",
  "seed": 42
}
```

返回 202：

```json
{
  "eval_run_id": "uuid",
  "status": "queued",
  "created_at": "2026-10-18T12:00:00Z"
}
```

MVP 不提供运行时退货规则配置 API，也不提供退款审批或退货人工审核公共 API。需要这些能力时必须另立契约，不能从现有管理端任意 JSON 配置绕过审计。

## 14. 错误码与稳定文案

API 使用工具错误码和以下协议级错误码：

| 错误码 | HTTP | 说明 |
|---|---:|---|
| `UNAUTHENTICATED` | 401 | 缺少/过期 access token |
| `CSRF_INVALID` | 403 | Origin/CSRF 校验失败 |
| `FORBIDDEN` | 403 | 角色无权限 |
| `REQUEST_IN_PROGRESS` | 409 | 同一聊天消息正在处理 |
| `DUPLICATE_REQUEST` | 409 | 已完成聊天消息被重复提交 |
| `CONFIRMATION_REQUIRED` | 409 | 创建退货申请缺少用户明确确认 |
| `VALIDATION_ERROR` | 400 | schema/字段错误 |
| `FILE_TOO_LARGE` | 413 | 上传文件超过 20 MiB |
| `UNSUPPORTED_FILE_TYPE` | 415 | 扩展名/MIME/魔数不受支持 |
| `UNSAFE_FILE` | 400 | 路径、符号链接、可执行内容或文件签名安全检查失败 |
| `RATE_LIMITED` | 429 | 限流 |
| `UPSTREAM_UNAVAILABLE` | 503 | 受控依赖不可用 |

服务端可以记录内部原因，但客户端只得到稳定 `code`、中文 `message`、`retryable` 和 `retry_after_ms`。

## 15. API 验收

1. OpenAPI schema 与本文所有路径、字段、枚举和错误响应一致。
2. 普通用户不能读取/修改他人会话、订单、物流、退货或工单。
3. support/admin 跨店铺请求被拒绝；admin 默认不能浏览消费者会话，只有显式 `support:conversation:read` 才可读取授权工单关联会话；质量标记只能作用于授权助手消息。
4. SSE 事件 fixture 覆盖七种事件、顺序、终止、取消、断线和错误。
5. 所有状态改变请求有 CSRF/Origin 防护、幂等或消息幂等保护。
6. 所有金额为整数分，所有时间带 UTC。
7. 政策 SSE 引用与知识版本元数据一致，无证据时不出现无引用断言。
8. 退货资格四项 decision 与布尔字段不变量一致；非 eligible 令牌不能创建申请。
9. `/api/v1/system/meta` 和事实响应中的 synthetic 标识足以支持阶段 11 的演示数据横幅。
10. 消费者只能读取本人 handoff；客服工单队列、详情、状态变更和会话 schema 足以支撑阶段 11 客服工作台。

本文件为阶段 3 契约。接口“可用”必须等到后续 API 实现、OpenAPI 检查和集成测试提供实际证据后才能声明。
