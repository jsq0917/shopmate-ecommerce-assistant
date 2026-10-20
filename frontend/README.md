# ShopMate 前端（阶段 11）

Vue 3 + Vite + TypeScript 实现的电商智能客服前端，包含消费者端、客服工作台与知识库管理端。
所有业务数据（价格、库存、政策、订单、退货资格）均来自后端结构化 API，前端不做任何推测或硬编码。

## 技术栈

| 类别 | 选型 |
|---|---|
| 框架 | Vue 3（`<script setup lang="ts">`）+ Pinia + Vue Router |
| 构建 | Vite 6 |
| UI | Element Plus（全中文文案） |
| 类型 | TypeScript strict（`noUnusedLocals` / `noUnusedParameters` / `verbatimModuleSyntax`） |
| 单测 | Vitest（jsdom + @vue/test-utils） |
| E2E | Playwright |

## 目录结构

```text
frontend/
├── src/
│   ├── api/           # API client：信封解包、错误码、SSE 解析、各端点封装
│   ├── stores/        # Pinia：auth（认证）、system（合成数据元信息）
│   ├── router/        # 路由与守卫（认证 / 角色）
│   ├── composables/   # useChatStream：SSE 事件状态机
│   ├── components/    # chat / catalog / orders / support / admin / common
│   ├── views/         # 页面组件（含 keep-alive 的 ChatView）
│   ├── utils/         # 金额、时间、状态标签等纯格式化函数
│   └── test/          # 测试 setup 与 fixture 工厂
├── e2e/               # Playwright 用例与演示数据 fixture
└── dist/              # 构建产物（已 gitignore）
```

## 环境配置

复制 `.env.example` 为 `.env` 后按需调整：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | API 前缀，前端始终同源调用 |
| `VITE_DEV_PORT` | `5173` | 开发服务器端口 |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | dev server 的 `/api` 反代目标 |
| `PLAYWRIGHT_BASE_URL` | `http://localhost:5173` | E2E 访问的前端地址 |
| `E2E_SHOPPER_EMAIL` / `E2E_SHOPPER_PASSWORD` | 见文件 | E2E 演示账号凭证 |

## 常用命令

```bash
npm install

npm run dev          # 开发服务器（/api 代理到 VITE_API_PROXY_TARGET）
npm run typecheck    # vue-tsc 严格类型检查
npm run test:run     # Vitest 单测（watch 模式用 npm run test）
npm run build        # 生产构建到 dist/
npm run preview      # 预览构建产物
npm run test:e2e     # Playwright E2E（需先准备后端与演示数据，见 e2e/README.md）
```

> 生产部署：把 `dist/` 内容作为静态资源由 Nginx 托管，`web/nginx.conf` 已配置 `/api` 反代
>（`proxy_buffering off` 以支持 SSE）与 SPA fallback。

## 设计约束（不可违反）

1. **中文 UI**：所有文案、状态标签、错误提示均为中文。
2. **不硬编码业务值**：价格、库存、政策文案、退货规则一律来自 API；未知值显示 `unknown` 或「暂无数据」，由用户自行判断，系统不推测。
3. **不暴露敏感信息**：access token 仅存内存（不写 localStorage / URL / 日志）；界面不展示 `trace_id`、`request_id`、完整 PII（联系方式、地址、运单号统一使用后端返回的 `*_masked` 字段）。刷新登录依赖 HttpOnly refresh cookie + 可读 CSRF cookie 拼 `X-CSRF-Token` 头。
4. **权限仅在后端生效**：前端的角色菜单与路由守卫只是体验层，不构成安全边界，真正的校验由 API 完成。
5. **写操作幂等**：退货申请与转人工提交均携带 `Idempotency-Key`；聊天消息携带 `client_message_id`。
6. **退货语义**：提交申请只代表进入审核流程（`refund_status=not_created`），界面明确提示「不等于退款成功」。

## 错误与状态处理

- 统一三态组件 `components/common/StateBlock.vue`：加载（骨架屏）、错误（可重试）、空状态。
- SSE 场景区分三种终止：`stopped`（用户主动停止）、`network`（断线，可重试）、`error`（流内错误事件，展示服务端错误码文案）。
- 发送后一律以服务端历史消息为准重新加载，避免前端出现「本地有、库里没有」的消息。
- 半截回答会标注「未完成」，非正常结束提供重试与转人工入口。

## 已知后端缺口

以下页面已按 `docs/06-api.md` 契约实现，但对应端点尚未在后端注册，运行期会呈现错误态，后端补齐后即通：

- `/api/v1/support/*`（客服工作台全部接口）
- 管理端的文档上传、`POST /admin/documents/{id}/reindex`、`PATCH` / `DELETE /admin/chunks/{id}`
