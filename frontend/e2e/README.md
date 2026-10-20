# E2E（Playwright）

覆盖阶段 11 的关键用户旅程：认证与路由守卫、聊天 SSE、商品搜索与比较、订单物流与退货、转人工。

## 前置条件

1. **后端 API 可用**。推荐用本机进程启动（不要改动任何 Docker 容器）：

   ```bash
   cd /e/project/shopmate-ecommerce-assistant
   DATABASE_URL="postgresql+asyncpg://shopmate:change-me-local-only@localhost:5432/shopmate" \
   REDIS_URL="redis://:change-me-local-only@localhost:16379/0" \
   MILVUS_HEALTH_URL="http://localhost:9091/healthz" \
   MILVUS_URI="http://localhost:19530" \
   EMBEDDING_MODEL_PATH="models/bge-m3" \
   APP_ENV=demo \
   RATE_LIMIT_AUTH_PER_MINUTE=1000 \
   .venv/Scripts/python.exe -m uvicorn shopmate_ecommerce_assistant.main:app --host 127.0.0.1 --port 18001
   ```

   加载本地嵌入模型约需 60 秒，确认就绪：`curl http://127.0.0.1:18001/ready` 应返回 200。

   > `RATE_LIMIT_AUTH_PER_MINUTE=1000` 仅用于测试窗口：后端对登录/注册/刷新默认限流 10 次/分钟，
   > 多个用例连续登录会触发 429。该值通过环境变量注入，不落盘、不改文件。

2. **生成演示数据**（幂等，可反复执行）：

   ```bash
   cd frontend
   node e2e/fixture.mjs
   ```

   该脚本会注册演示账号（`E2E_SHOPPER_EMAIL` / `E2E_SHOPPER_PASSWORD`，见 `.env.example`）、
   写入一条已签收的合成订单及其物流事件，并清理上一轮遗留的退货申请，最后产出 `e2e/.fixture.json`
   供用例消费。三种状态（全新 / 半成品 / 已完成）均已验证幂等。

## 运行

```bash
cd frontend
VITE_API_PROXY_TARGET=http://localhost:18001 npx playwright test
```

Playwright 会自动拉起 `npm run dev`（通过 webServer 配置），并把 `/api` 代理到上述目标。

## 浏览器通道

配置默认使用 `channel: 'msedge'`，直接复用 Windows 预装的 Edge，避免上百 MB 的浏览器下载。
若本地没有 Edge，先执行 `npx playwright install chromium`，再删除 `playwright.config.ts` 中的
`channel: 'msedge'` 一行。

## 用例一览

| 文件 | 覆盖内容 |
|---|---|
| `auth.spec.ts` | 未登录重定向、错误密码提示、登录落地首页、刷新保持登录、消费者看不到客服/管理入口 |
| `chat.spec.ts` | 会话新建、SSE 流式渲染（含「正在回复」中间态）、停止生成、消息持久化 |
| `catalog.spec.ts` | 关键词搜索、商品卡片价格/库存/数据更新时间、详情、两件比较 |
| `order-return.spec.ts` | 订单详情、物流时间线、退货资格检查、提交申请与「未退款」提示 |
| `handoff.spec.ts` | 转人工表单校验、工单创建成功与工单列表 |

## 断言原则

- 登录成功与否必须断言**首页真实元素**（如 `.sm-composer-input`），不能只断言导航链接——
  导航在部分状态下未登录也可见，也不能用可被 `/login?next=/` 误匹配的宽松 URL 正则。
- 验证码为服务端签发的算式题，读取前需等待题目就绪（否则会读到「加载中…」）。
- 测试失败时先怀疑产品本体；只有在确认是选择器或时序问题后才修改测试，
  禁止通过放宽或删除断言让用例变绿。

## 产物

失败用例的截图与错误上下文写入 `test-results/`（已被 gitignore）。
