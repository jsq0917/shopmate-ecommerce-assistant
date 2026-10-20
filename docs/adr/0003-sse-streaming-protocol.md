# ADR-0003：聊天流式输出采用 POST + SSE 稳定事件协议

- 状态：已接受
- 日期：2026-10-18
- 阶段：阶段 3
- 相关文档：`docs/03-architecture.md`、`docs/06-api.md`

## 背景

ShopMate 聊天需要：

- 在服务端完成认证、会话归属、工具调用、RAG 和引用校验后再流式返回文本。
- 前端可以分别渲染工具状态、商品卡片、引用、文本增量和错误。
- 事件结构由后端决定，不能把模型原始控制文本当作协议。
- 断线、取消、工具失败和资源耗尽时有明确状态，不把半截回答当成成功。

浏览器原生 `EventSource` 只支持 GET，且自定义 Authorization header 能力受限；聊天请求通常需要 POST body、Bearer token、CSRF 和 `client_message_id`。

## 决策

聊天使用：

```http
POST /api/v1/chat/stream
Content-Type: application/json
Accept: text/event-stream
```

响应使用 `text/event-stream`，前端通过 `fetch` + `ReadableStream` 读取，不依赖原生 `EventSource`。

### 稳定事件

业务事件固定为七种：

```text
meta
tool_status
product_card
citation
delta
done
error
```

每个事件使用统一 envelope：

```json
{
  "schema_version": "1.0",
  "event_id": "1",
  "request_id": "uuid",
  "sequence": 1,
  "occurred_at": "2026-10-18T12:00:00Z",
  "type": "meta",
  "data": {}
}
```

SSE 的 `id:` 与 `event_id` 一致，`event:` 与 `type` 一致。`sequence` 从 1 递增。模型输出只能进入 `delta.data.text`，不能生成/改变事件类型、引用、价格、库存或完成状态。

### 顺序与终止

1. `meta` 必须是首个业务事件且只出现一次。
2. `tool_status`、`product_card`、`citation`、`delta` 可以按处理过程出现。
3. 最后必须且只能有一个终止事件：`done` 或 `error`。
4. `done.finish_reason` 为 `stop/refusal/handoff/cancelled`。
5. `error` 必须包含稳定 `error_code`、中文安全 `user_message`、`retryable` 和 trace。
6. 每个 `product_card` 的价格/库存必须来自结构化工具；每个 `citation` 必须来自本轮实际片段。
7. `done` 携带 `message_is_complete`：正常回答为 true，取消为 false；`error` 的部分快照使用 `partial_persisted` 和 `partial_message_id` 表示。

完整字段见 `docs/06-api.md` 第 7 节。

### 认证与错误

- 流建立前完成认证、会话归属、CSRF、限流和输入长度检查。
- 建立前失败返回普通 HTTP JSON 错误；建立后失败发送终止 `error` 事件。
- HTTP 响应建立成功后通常为 200，即使最终业务失败也通过 `error` 事件结束。
- 不在 URL 中放 token、用户 ID 或完整订单信息。

### 取消、断线与重试

- 客户端取消通过 abort HTTP 连接；服务端停止 LLM/工具调用并释放资源。
- 助手流内容先在受控内存/Redis 缓冲，终止时一次性写入 `messages`，落库后正文不可修改。
- 若连接仍可写，先保存取消快照再发送 `done(finish_reason=cancelled, message_is_complete=false)`；否则仍尽量保存 `is_complete=false` 的部分快照供历史读取。
- 保活使用 SSE 注释行，不作为业务事件。
- MVP 使用 `client_message_id` 防止重复用户消息：处理中返回 `REQUEST_IN_PROGRESS`，已完成返回 `DUPLICATE_REQUEST`。
- MVP 不支持 `Last-Event-ID` 断点续传或服务端流重放。断线后客户端读取历史，显示未完成状态，再由用户发起新请求。

## 为什么不使用其他方案

### 原生 EventSource

不能发送 POST body 和标准 Authorization header；用 query token 会泄露凭据，用跨站 cookie 会增加 CSRF 面。未采用。

### WebSocket

双向连接对本 MVP 的“客户端提交问题、服务端返回事件”不是必需能力；需要额外的认证、心跳、消息路由和连接管理。未采用。若未来加入坐席实时双向聊天，再单独 ADR 评估。

### 普通 JSON + 轮询

实现简单，但首 token 延迟、工具状态和增量文本体验差，还增加轮询负载。未作为聊天协议。

### SSE 断点续传/事件日志

需要持久事件游标、跨实例重放和敏感内容保留策略，超出 MVP。当前采用“历史消息恢复 + 新请求”的明确降级。

## 后果

正面：

- 可以使用标准 Bearer/CSRF，并保持流式增量。
- 前端按固定事件渲染，模型不能污染协议。
- 引用、商品卡片和工具状态与文本解耦，易做 fixture、组件和 E2E 测试。
- 单连接单向流符合聊天主流程，代理和故障边界较简单。

负面/风险：

- 代理必须禁用缓冲，连接超时和资源限制要专门配置。
- `fetch` 客户端需要自行解析 SSE 分帧、处理多行/半包和 JSON 校验。
- 无断点续传；长回答断线时需要读取历史重试。
- 需要防止流建立后输出未完成却被标记成功；必须以终止事件和持久化状态双重判断。

## 实施与验证

1. 阶段 10 实现事件 builder 与 Pydantic schema；事件 JSON 必须使用 `ensure_ascii=false` 的稳定编码。
2. 测试七种事件的 fixture、顺序、重复 meta、缺失终止、重复终止和非法 payload。
3. 测试建立前认证失败、建立后上游失败、客户端 abort、总超时和依赖故障。
4. 前端测试逐帧解析、半包、断线提示、未完成消息恢复和组件卸载关闭连接。
5. 生产关闭代理缓冲，记录首 token/总耗时；任何“流式可用”结论必须有集成测试或可复现运行证据。
