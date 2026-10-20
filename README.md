# ShopMate 电商智能客服与轻导购助手

可追溯的电商 AI 客服系统：**结构化事实来自 PostgreSQL、政策回答带引用、退款/赔付由确定性规则和人工决定**。  
模块化单体（FastAPI + Vue 3 + PostgreSQL + Redis + Milvus + 本地 BGE-M3），单 Agent + 确定性工具层，不拆微服务。

> 全部商品、订单、物流、政策与评测数据均为 **synthetic / mock**。不接真实支付、真实退款、真实优惠券，也不含真实用户 PII。



---

## 1. 它能做什么

| 能力                  | 实现方式                                                          | 关键约束                               |
| ------------------- | ------------------------------------------------------------- | ---------------------------------- |
| 商品搜索 / 详情 / 比较 / 库存 | `tools/` 结构化查询 PostgreSQL                                     | 价格、库存、SKU 只来自数据库，带 `as_of`         |
| 退换货/配送/保修政策问答       | BGE-M3 dense+sparse 双路检索 + RRF + 引用                           | 无证据则拒答，引用含文档/章节/版本/生效期/片段 ID       |
| 订单与物流查询             | 归属校验后的结构化工具                                                   | 只能查自己的订单；日志脱敏                      |
| 退货资格与申请             | 规则引擎 + 幂等写操作                                                  | 申请 ≠ 退款；LLM 不能批准资金                 |
| 投诉/法律威胁/大额异常        | 风险识别 → 人工工单                                                   | 高风险不自动承诺，幂等建单                      |
| 流式聊天                | SSE：`meta/tool_status/product_card/citation/delta/done/error` | 事件结构由后端决定，不由模型决定                   |
| 管理端                 | 知识库/文档/片段/评测只读接口                                              | 部分写接口尚未实现，见 §9                     |
| 评测与压测               | 136 条业务评测 + 58 条检索金标 + Locust                                 | 数字全部来自实际运行，见 `docs/eval-report.md` |

不在范围内：真实支付/退款、K8s、微服务、消息队列、多 Agent、模型微调。

---

## 2. 架构与目录

```text
Vue 3 (web/nginx 反代 /api)
        │ HTTPS + SSE
        ▼
FastAPI ── Auth/JWT/CSRF/限流 ── 输入护栏 ── 意图路由 ── 输出护栏
   │            │                     │
   │            │                     ├─ 结构化路径 → PostgreSQL / Redis
   │            │                     ├─ 知识路径   → Milvus + PostgreSQL 元数据
   │            │                     └─ 规则路径   → 退货资格 / 转人工
   └─ 结构化日志 / 审计 / 指标
```

| 路径                                  | 内容                                           |
| ----------------------------------- | -------------------------------------------- |
| `src/shopmate_ecommerce_assistant/` | API、domain 规则、tools、rag、safety、observability |
| `frontend/`                         | Vue 3 + Vite + TS（消费者端、客服端、管理端）              |
| `web/`                              | Nginx 配置与生产前端镜像（`Dockerfile.prod`）           |
| `alembic/`                          | 数据库迁移（4 个版本，空库可升到 head）                      |
| `scripts/`                          | seed / ingest / 评测 / 压测 / 演示账号 / 部署安全复查      |
| `data/`                             | 合成数据、知识源文件、评测集（seed 生成 + 手写用例）               |
| `docs/`                             | PRD、架构、数据/工具/API 契约、安全、测试、评测、部署              |

文档索引见 [`docs/README.md`](docs/README.md)。

---

## 3. 环境要求

| 组件             | 版本                     | 说明                              |
| -------------- | ---------------------- | ------------------------------- |
| Docker Desktop | 4.x+（Linux containers） | 已实测 Docker 29.8 / Compose v5.5  |
| Python         | 3.12                   | `.python-version`；用 `uv` 管理     |
| uv             | 0.12.x                 | `pip install uv` 或官方安装脚本        |
| Node.js        | 22.x                   | 前端构建与 Playwright（仅开发需要）         |
| 内存             | ≥ 8 GB（建议 16 GB）       | BGE-M3 权重约 2.3 GB，CPU 推理常驻数 GB  |
| 磁盘             | ≥ 15 GB                | 镜像 + Milvus/PostgreSQL 卷 + 模型权重 |

模型权重**不进仓库、不进镜像**，需自行放置：

```bash
# 期望目录：./models/bge-m3（含 config.json / pytorch_model.bin / tokenizer 等）
# 可用 huggingface-cli 或 modelscope 下载 BAAI/bge-m3
```

缺少权重时 API 仍可启动：政策问答会降级为“知识库暂不可用”，商品/订单/退货/转人工不受影响。

---

## 4. 快速开始（Docker，推荐）

### 4.1 准备配置

```bash
cp .env.example .env
# 编辑 .env：至少替换 POSTGRES_PASSWORD / REDIS_PASSWORD / MINIO_ROOT_PASSWORD
# 并保持 DATABASE_URL / REDIS_URL 中的口令与上面一致（本机脚本会用它们连容器）
```

`.env` 已在 `.gitignore` 中，禁止提交。

### 4.2 启动

```bash
docker compose config --quiet          # 先校验编排
docker compose up -d postgres redis etcd minio milvus
docker compose ps                       # 等 5 个依赖变为 healthy
docker compose up -d api web            # api 首次启动会自动执行 alembic upgrade head
```

端口（可用 `.env` 覆盖）：API `8000`、前端 `3000`、PostgreSQL `5432`、Redis `6379`、Milvus `19530/9091`、MinIO `9000/9001`。

> `3000` 上的 web 容器是**占位页**（阶段 4 脚手架），只能用来验证反代链路；真实 UI 见 §4.5。

> **不会自动做的事**：不启动、不重建、不删除任何已有容器或数据卷。需要重置数据时必须显式执行并自行承担后果。

### 4.3 迁移与合成数据

```bash
# 迁移（容器内已在启动时执行；手动执行用）
uv run alembic upgrade head

# 合成数据：30+ 商品、100 订单、政策/FAQ/评测集；幂等，可重复执行
uv run python scripts/seed.py

# 知识入库（需要 ./models/bge-m3 与 Milvus 就绪）
uv run python scripts/ingest.py
```

`seed.py` 会写 `data/` 下的 JSON/JSONL（含评测集）并 upsert 数据库；重复执行不会产生重复行，**也不会覆盖已存在的手写评测用例**。

### 4.4 演示账号

种子账号默认是“可存在但不可登录”的哨兵哈希（保证订单/工单外键完整）。给三个合成账号设置演示口令：

```bash
uv run python scripts/demo_accounts.py --dry-run   # 先看会改哪些账号
uv run python scripts/demo_accounts.py             # 实际写入 Argon2 哈希
```

| 账号                          | 角色      | 用途                |
| --------------------------- | ------- | ----------------- |
| `shopper01@example.invalid` | shopper | 消费者旅程（自带 seed 订单） |
| `support01@example.invalid` | support | 客服视角（工单数据）        |
| `admin01@example.invalid`   | admin   | 管理端只读接口           |

演示口令：`ShopMate-Demo-Only-2026`（合成演示凭据，**不是密钥**；共享环境务必用 `--password` 或 `SHOPMATE_DEMO_PASSWORD` 覆盖）。登录页需要算式验证码，按题干求和即可。

### 4.5 访问

> **先读这一句**：开发栈的 web 容器（`compose.yaml` 的 `web` 服务）只提供 `web/public/` 下的
> **阶段 4 占位页**，**不是消费者界面，也没有登录功能**。要看到并登录真实 UI，请用下面三条路径之一。

| 路径 | 适用场景 | 命令 | 访问地址 |
|---|---|---|---|
| **(a) 前端开发服务器**（推荐） | 看完整 UI、改前端代码 | 见 §5：`cd frontend && npm ci && npm run dev`（`/api` 代理到 `8000`） | <http://localhost:5173> |
| **(b) 生产前端镜像** | 验证生产构建产物，不想启整套生产栈 | `docker build -f web/Dockerfile.prod -t shopmate-web:0.1.0 .`，然后 `docker run -d --name shopmate-web-prod -p 8080:8080 --network shopmate_default --read-only --tmpfs /tmp --tmpfs /var/cache/nginx --cap-drop ALL --security-opt no-new-privileges:true shopmate-web:0.1.0` | <http://localhost:8080> |
| **(c) 完整生产栈** | 发布前验收 | 见 §8（`compose.prod.yaml`，含 `migrate`、只读根文件系统、仅 `8080` 对外） | <http://localhost:8080> |

- 路径 (b) 要求开发栈已经 `up -d api`：镜像里的 Nginx 把 `/api` 反代到 `api:8000`，靠 `shopmate_default` 网络里的服务别名解析。
- 路径 (b)/(c) 的 UI 是否可用取决于 `api` 容器跑的是**当前代码**——如果你继承的是旧容器，先重建 API 镜像或改用路径 (a)。
- 三条路径都需要先完成 §4.3（迁移 + seed）与 §4.4（演示账号），否则登录会失败（账号口令未设置）。
- 若 `8000` 被其他进程占用，路径 (a) 可换端口：`cd frontend && VITE_API_PROXY_TARGET=http://127.0.0.1:18001 npm run dev`（后端用 `--port 18001` 启动）。

API 侧（与路径无关）：

- API 文档（OpenAPI）：<http://localhost:8000/docs>
- 健康检查：`/health`（进程存活）、`/ready`（PG/Redis/Milvus 就绪）

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

---

## 5. 本地开发（混合模式）

依赖跑在容器里，API/前端跑在宿主机，改代码即时生效：

```bash
docker compose up -d postgres redis etcd minio milvus
uv sync
uv run alembic upgrade head
uv run uvicorn shopmate_ecommerce_assistant.main:app --reload --port 8000

# 另开终端
cd frontend && npm ci && npm run dev        # http://localhost:5173，/api 代理到 8000
```

`.env` 中的 `DATABASE_URL` / `REDIS_URL` 指向 `localhost`，容器口令必须与之一致。生产环境**关闭 `--reload`**（见 `compose.prod.yaml`）。

---

## 6. 测试与质量门禁

```bash
uv sync
uv run ruff check .
uv run pytest                     # 单元 + 集成 + 安全；需要 PG/Milvus 的用 integration 标记
uv run pytest tests/security
uv run pytest -m integration      # 显式运行集成测试
```

```bash
cd frontend
npm ci
npm run typecheck
npm run test:run                  # Vitest
npm run build
npm run test:e2e                  # Playwright（需先起 API/前端，见 frontend/README.md）
```

```bash
uv run python scripts/check_deploy_security.py   # 部署安全静态复查（34 项）
uv run python scripts/verify_stage13.py          # 从评测原始结果复算头条指标
```

最近一次实测结果记录在 `docs/test-report.md`、`docs/eval-report.md`、`docs/project-status.md`。任何“通过”都以命令输出为准，本 README 不复述未复跑的数字。

---

## 7. 评测与压测

```bash
# 检索 + 业务行为（不需要外部 LLM）
uv run python scripts/eval_stage13.py --parts retrieval business --output /tmp/eval.json

# 生成质量（需要 OpenAI 兼容端点，例如本机 Ollama）
uv run python scripts/eval_stage13.py --parts generation \
  --llm-base-url http://localhost:11434/v1 --llm-model qwen2.5:7b

# 压测（另开 API 后；--host 必填，否则 locust 默认打 locust 自己的 web 端口）
# 脚本默认账号见 scripts/locustfile.py docstring（SHOPMATE_LOAD_EMAIL/PASSWORD），
# 且脚本要求把 RATE_LIMIT_CHAT_PER_MINUTE 放宽（默认 20/min 会把测试变成 429 测量）；
# 脚本内的 18001 口径来自阶段 13 评测环境，可换成本机实际端口。
uv run --with locust locust -f scripts/locustfile.py --headless \
  -u 20 -r 5 -t 2m --host http://127.0.0.1:8000 --only-summary
```

指标定义、baseline 对照、失败案例与复现命令见 [`docs/eval-report.md`](docs/eval-report.md)。

---

## 8. 生产部署

```bash
cp .env.prod.example .env.prod && ${EDITOR} .env.prod     # 全部替换为强随机值；TRUSTED_HOSTS 保留 127.0.0.1,localhost
docker build -t "${API_IMAGE:-shopmate-api:0.1.0}" .            # 编排不含 build 段，镜像需先构建
docker build -f web/Dockerfile.prod -t "${WEB_IMAGE:-shopmate-web:0.1.0}" .
docker compose -f compose.prod.yaml --env-file .env.prod config --quiet
docker compose -f compose.prod.yaml --env-file .env.prod up -d postgres redis etcd minio milvus
docker compose -f compose.prod.yaml --env-file .env.prod run --rm migrate
docker compose -f compose.prod.yaml --env-file .env.prod up -d api web
```

生产差异概要（完整说明见 [`docs/08-deployment.md`](docs/08-deployment.md)）：

- 独立项目名 `shopmate-prod` 与独立数据卷，不与开发栈混用；
- 只有 `web` 暴露 `8080`，数据服务仅内网；TLS 由上游边缘代理终结；
- `api`/`web`：非 root、`read_only`、`cap_drop: ALL`、`no-new-privileges`、CPU/内存上限；
- 关闭 `--reload`，迁移拆成一次性 `migrate` 服务，API 单 worker（BGE-M3 权重在进程内单例）；
- 全部服务 `json-file` 日志轮转（10 MB × 3），镜像固定 tag/digest，不挂 Docker socket。

首次部署检查清单：[`docs/09-release-checklist.md`](docs/09-release-checklist.md)。备份/恢复与故障处理见部署手册第 6、8 章。

---

## 9. 已知限制（阶段 14 现状）

| 项                             | 现状                                    | 影响                                           |
| ----------------------------- | ------------------------------------- | -------------------------------------------- |
| 开发栈 web 容器（`localhost:3000`） | 只 COPY `web/public/`，是**阶段 4 占位页** | 无法登录、无聊天界面；看真实 UI 走 §4.5 的 (a)/(b)/(c) |
| `GET/PATCH /api/v1/support/*` | 契约已定义（`docs/06-api.md` §12），**后端未注册** | 前端客服工作台显示错误态；可用 `GET /api/v1/handoff` 查看本人工单 |
| 管理端文档上传 / 重建索引 / 片段编辑         | **未实现**                               | 管理端知识页面部分操作不可用；入库请用 `scripts/ingest.py`      |
| 管理端只读接口                       | 已实现（知识库、文档、片段、评测历史、模型配置）              | —                                            |
| 多副本横向扩展                       | 不支持                                   | 单 worker + 进程内 BGE-M3；扩展需拆独立 embedding 服务    |
| 真实数据接入                        | 未实现                                   | 仅合成数据；Mock OMS，非真实订单系统                       |
| Alembic 自动迁移                  | 仅开发 compose 的 API 启动时执行               | 生产走独立 `migrate` 服务，避免并发迁移                    |

---

## 10. 安全与合规基线

- 密码 Argon2；JWT 短过期 + 刷新令牌轮换；登录/注册有算式验证码与 Redis 限流。
- 订单/物流/退货/工单全部后端校验 `user_id` 与 `shop_id` 归属；管理端要求 admin 角色。
- 检索内容视为**不可信数据**，文档中的指令不能改变系统规则或工具权限。
- 写操作需 `idempotency_key`，重复提交不产生第二条记录。
- 日志不记录完整手机号、地址、证件号、银行卡或系统 prompt；`scripts/check_deploy_security.py` 静态复查 PII 与明文密钥。
- 业务铁律、威胁模型与安全验收见 [`docs/07-security.md`](docs/07-security.md)。

---

## 11. 常见问题（详见部署手册第 8 章）

| 现象                           | 处理                                                                       |
| ---------------------------- | ------------------------------------------------------------------------ |
| `/ready` 返回 503              | 看 `docker compose ps` 是否 healthy；`docker compose logs --tail=100 milvus` |
| 政策问答总说“知识库暂不可用”              | 权重未挂载 / Milvus 未入库；检查 `./models/bge-m3` 并跑 `scripts/ingest.py`           |
| 登录后立刻跳回登录页                   | 前端与 API 不同源导致 CSRF cookie 丢失；用 compose 的 web 端口访问，或检查 vite 代理            |
| 登录报 429                      | 认证限流（默认 10 次/分钟）；等一分钟或调 `RATE_LIMIT_AUTH_PER_MINUTE`                     |
| 前端页面 404 报错提示                | 见 §9 未实现端点                                                               |
| `docker compose config` 报缺变量 | 生产必须用 `--env-file .env.prod`，且 `*_IMAGE`、`*_PASSWORD`、`*_SECRET` 不能留空    |

---

## 12. 文档

| 文件                             | 内容                    |
| ------------------------------ | --------------------- |
| `docs/02-prd.md`               | 产品需求、MVP、验收标准         |
| `docs/03-architecture.md`      | 组件图、时序、三条路径、降级        |
| `docs/04-data-contract.md`     | 表、字段、索引、状态机           |
| `docs/05-tool-contract.md`     | 工具输入输出、错误码、幂等         |
| `docs/06-api.md`               | REST/SSE 契约与实现现状      |
| `docs/07-security.md`          | 威胁模型、PII、护栏、发布门禁      |
| `docs/08-deployment.md`        | 生产部署、迁移、备份/恢复、故障处理    |
| `docs/09-release-checklist.md` | 全新环境启动与发布检查清单         |
| `docs/demo.md`                 | 3 分钟 / 10 分钟演示脚本      |
| `docs/resume-evidence.md`      | 简历/面试证据台账：指标口径、实现状态三分、缺陷定位 |
| `docs/interview-prep.md`       | 中文简历项目描述 + 15 个面试问答提纲 + 数字速查卡 |
| `docs/test-report.md`          | 测试与安全验收               |
| `docs/eval-report.md`          | 评测集、指标、baseline 对照、压测 |
| `docs/project-status.md`       | 各阶段实施与验收记录            |
