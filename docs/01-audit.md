# 阶段 1 只读审计与架构初稿

> 阶段：阶段 1 — 只读审计与 GitHub 调研  
> 审计日期：2026-10-18（Asia/Shanghai）  
> 审计性质：只读。未修改业务代码，未启动/停止/删除容器，未提交 Git，未修改参考目录。

## 1. 审计范围与方法

本次审计：

- 核对当前项目根目录、脚手架、Git 状态、依赖和基础配置。
- 只读审阅 `E:\AI大模型开发\eduRAG(陈杰老师)\Itcast_qa_system` 的结构、技术栈、API、RAG 模块、测试和 Docker 方式。
- 使用 GitHub REST API/网页元数据调研四个公开参考仓库；未 clone 大型仓库。
- 只读取完成任务所需的文件；未递归扫描视频、模型权重、缓存、`node_modules` 或 `.git` 内部对象。
- 未执行任何 Docker 启停命令，未运行 `docker compose up/down`，未删除容器或卷。

## 2. 当前项目基线

### 2.1 目录与 Git

- 工作目录：`E:\project\shopmate-ecommerce-assistant`
- 当前分支：`main`
- 提交状态：**阶段 0 当时**尚无 commit（现状：2026-10-23 已有 7 个提交、4 个已推送，见 `docs/project-status.md` §0.2）
- 现有内容全部为未跟踪文件；本阶段新增的三份文档也属于未跟踪的 `docs/` 目录内容。

当前基线文件：

| 路径 | 事实 | 审计结论 |
|---|---|---|
| `AGENTS.md` | 1551 行项目合同 | 已完整读取，作为最高优先级项目约束 |
| `.gitignore` | 仅覆盖部分 Python 生成物和 `.venv` | 尚未覆盖 `.env`、`node_modules`、日志、测试产物和常见 IDE/OS 文件 |
| `.python-version` | `3.12` | 与合同一致 |
| `pyproject.toml` | uv 项目；`requires-python >=3.12`；`dependencies = []` | 依赖基线为空；尚未生成 `uv.lock` |
| `README.md` | 0 字节 | 尚无启动、架构、演示或安全说明 |
| `src/shopmate_ecommerce_assistant/__init__.py` | 仅默认 `main()` 打印示例 | 尚未有业务代码 |

### 2.2 当前依赖与密钥检查

- 当前运行时代码没有第三方依赖，因此不存在“代码引用了未声明依赖”的已确认问题。
- 当前项目运行时代码和脚手架中未发现 API Key、密码、私钥、连接串或真实 `.env` 文件。
- 当前项目没有 Windows 绝对路径或硬编码 `localhost` 运行配置。
- `pyproject.toml` 仍有占位描述 `Add your description here` 和作者邮箱元数据；邮箱不是密钥，但发布前应确认是否保留。
- 阶段 0 已记录 `SSL_CERT_DIR=D:\dev\anaconda3\Library\ssl\certs`，该目录没有有效证书文件。后续下载依赖前必须在不修改系统配置的前提下处理，否则可能影响 HTTPS 访问。

### 2.3 当前缺口

1. 没有 `uv.lock`，无法形成可复现的 Python 依赖解析基线。
2. 没有 `compose.yaml`、`.env.example`、`Dockerfile`、健康检查或启动说明。
3. 没有测试目录、测试配置、lint/type-check 配置或 CI。
4. `.gitignore` 未覆盖 `.env` 和前端/测试产物，存在后续误提交风险。
5. 尚无业务模块、API、数据库模型或前端工程，本阶段无法验证运行时接口。
6. 当前仓库没有首个 commit，回滚基线尚不存在；未经用户明确同意不得提交。

## 3. 参考项目快照：Itcast_qa_system

### 3.1 元数据与许可证

| 项目 | 观察结果 |
|---|---|
| 只读路径 | `E:\AI大模型开发\eduRAG(陈杰老师)\Itcast_qa_system` |
| Git 分支 | `v1.1` |
| 远程 | `github.com:JayChen123/itcast_qa_system.git` |
| 最新本地 commit | `de6aad052d00566e21c47bbdbbdb9d10869bf05f` |
| Commit 日期 | `2026-07-31T08:51:40+08:00` |
| Commit 标题 | `fix api key` |
| 许可证文件 | 未发现根目录或递归扫描到的 `LICENSE`、`LICENCE`、`COPYING`、`NOTICE`、`UNLICENSE` |
| README 许可证声明 | 未发现许可证或版权声明 |
| 使用结论 | **许可证无法确认，只能借鉴设计思想；禁止复制代码、配置、数据、模型资产和提示词原文** |

本地快照还存在未提交变更：包括暂存的 `__pycache__` 文件、删除的 Compose 文件、修改的 notebook 和测试演示脚本。审计未修改、暂存、恢复或清理这些内容，也没有复制它们。

### 3.2 技术栈与模块结构

从 `pyproject.toml`、目录和关键文件观察：

- Python 3.12、uv，`uv.lock` 与 `requirements.txt` 同时存在。
- FastAPI + Uvicorn，提供 HTTP/WebSocket 入口。
- MySQL、Redis、Milvus 作为数据/检索基础设施。
- BGE-M3/FlagEmbedding、BERT 分类器、reranker 等本地模型相关依赖。
- 主要目录：
  - `base/`：配置、日志等基础能力。
  - `mysql_qa/`：MySQL FAQ、BM25、Redis 缓存和预处理。
  - `rag_qa/`：文档加载、OCR、分块、向量库、查询分类、RAG 编排和评测。
  - `demo/`、`notebooks/`：课程演示与手工实验。
  - `static/`：静态页面和未完整接入的 React 草案。
  - `docker/`：分拆的基础设施 Compose 文件。

### 3.3 后端 API 观察

`app.py` 中可直接观察到：

| 接口 | 作用 |
|---|---|
| `GET /` | 应用入口/页面 |
| `POST /api/create_session` | 创建会话 |
| `GET /api/history/{session_id}` | 获取历史 |
| `DELETE /api/history/{session_id}` | 删除历史 |
| `POST /api/query` | 非流式问答入口 |
| WebSocket `/api/stream` | 流式问答 |
| `GET /health` | 健康检查 |
| `GET /api/sources` | 查询知识源 |

该接口划分可作为“会话 + 问答 + 健康检查”的基础思路，但不能直接复制其鉴权、会话归属、错误处理和 CORS 实现。

### 3.4 RAG 与业务能力观察

- 文档加载包含 PDF、PPT、Markdown、图片/OCR 等方向。
- 支持文档分块和 Milvus 向量检索。
- 包含查询分类、策略选择、HyDE/子查询/回溯检索等探索性模块。
- 包含 MySQL FAQ/BM25 与向量检索的分层思路。
- `rag_qa/core/vector_store.py` 当前使用 `WeightedRanker` 的两路加权融合；这不是 ShopMate 已确认的 RRF 实现。
- 当前参考快照没有把三通道边界、结构化事实来源和工具权限收敛成统一契约。

可借鉴的是“FAQ/精确匹配 + 语义检索 + 生成”的分层思想；不可借鉴的是把多个策略未经评测直接叠加、或以课程演示替代业务验收。

### 3.5 测试与 CI

- 未发现 `tests/`、`test/` 或 `__tests__/` 目录。
- 未发现 `pytest.ini`、`tox.ini`、`conftest.py` 或 pytest 配置。
- 未发现 `.github/workflows`、GitLab CI、Jenkins CI。
- 唯一名为 `test_*.py` 的文件是 `notebooks/test_demo.py`，属于手工连接/演示脚本，不是自动化功能测试套件。
- `locust_test.py` 是压测脚本，不等同于功能测试或单元测试。
- 结论：不能声称参考项目具备自动化测试或 CI。

### 3.6 Docker 方式与风险

观察到三套 Compose 方向：根目录应用编排、`docker/base_app` 和 `docker/milvus_redis`。镜像使用固定版本是正面做法，但仍存在以下风险：

1. 根 `docker-compose.yml` 依赖外部 Docker network，并要求手工先创建网络。
2. 根 Compose 和 `Dockerfile` 存在 macOS 绝对路径/`WORKDIR`，不可移植到 Windows。
3. 配置、Compose、入口脚本中存在明文数据库、对象存储和缓存凭据；本文不复制具体值。
4. `docker/milvus_redis` 使用大量相对 bind mount，而合同要求 Milvus 使用 named volume。
5. 部分 Compose 依赖只使用 `depends_on` 列表，未全部等待依赖服务健康；服务启动顺序不可靠。
6. 某套 Compose 的 etcd advertise 地址使用容器内不可用的 localhost 形式，可能影响服务间发现。
7. 服务版本、密码和 healthcheck 分散在多个文件中，容易漂移。
8. 未执行 `docker compose config` 或启动验证；本阶段不启动容器。

### 3.7 路径、安全与依赖风险

| 风险 | 证据位置 | 对 ShopMate 的约束 |
|---|---|---|
| 模型/数据/日志绝对路径 | `base/config.py`、`rag_qa/core/vector_store.py`、`rag_qa/core/document_processor.py`、`Dockerfile` | 使用相对路径与环境变量；容器内使用 `/app` 受控目录 |
| 配置文件默认凭据 | `base/config.py`、Compose 文件、`entrypoint.sh` | 只从环境变量/密钥管理读取；不把值写入仓库或文档 |
| `eval()` 读取配置 | `base/config.py` | 禁止使用 `eval()` 解析配置；采用 JSON/Schema 校验 |
| CORS 全开放且允许凭据 | `app.py` 的 `allow_origins=["*"]` 与 `allow_credentials=True` | 按环境配置明确 origin；不默认全开放 |
| 宽泛异常捕获和错误信息回传 | `app.py`、`vector_store.py`、`document_processor.py` | 使用稳定错误码，服务端记录脱敏细节，客户端只收安全消息 |
| 前后端接口/端口不一致 | `static/src/App.jsx` 使用 `http://localhost:8000/query` 等路径；`app.py` 实际入口为 `/api/...`、端口 `8003` | 前端使用项目 API 客户端和相对路径，由 Vite 代理/环境配置处理 |
| 前端工程不完整 | 未见 `package.json`、Vite 配置；静态 HTML 与 React 草案并存 | 本项目必须从 Vue 3 + Vite + TypeScript 正式脚手架开始 |
| 依赖治理复杂 | `pyproject.toml`、`requirements.txt`、`uv.lock` 并存且含大量重型依赖 | ShopMate 只使用 `uv add` 维护单一依赖源并生成 `uv.lock` |
| 无自动化测试 | 第 3.5 节 | 每个领域规则和 API 契约必须配单元/集成测试 |
| 真实外部数据风险 | README/`order_service.py` 描述依赖其他项目订单数据 | 不复制数据；ShopMate 只使用标记为 synthetic 的 Mock OMS/种子数据 |

## 4. ShopMate 三通道架构初稿

ShopMate 采用模块化单体 + 单 Agent + 确定性工具层。所有入口先经过认证、店铺/会话归属和输入安全检查，再由意图路由选择三条主通道之一。

```text
Vue 3 Web
   | HTTPS / SSE
FastAPI API
   |-- Auth / Session / Rate limit / Input safety
   |-- Intent router + query rewrite
   |
   +-- A. 结构化购物与订单通道
   |      tools -> PostgreSQL / Redis cache / Mock OMS
   |      商品、SKU、价格、库存、优惠、订单、物流
   |
   +-- B. 文档知识 RAG 通道
   |      文档/版本/片段元数据 -> PostgreSQL
   |      向量与词法索引 -> Milvus
   |      强制 citation + effective/version filters
   |
   +-- C. 确定性规则与升级通道
   |      return eligibility / return request / handoff ticket
   |      idempotency + audit + risk escalation
   |
   +-- Answer composer -> output guard -> SSE events
   +-- Structured logs / metrics / traces
```

### 4.1 通道 A：结构化购物与订单

- 适用于商品搜索、详情、比较、价格、库存、优惠、订单和物流。
- 数据源：PostgreSQL 为主；Redis 只做短期、受控缓存；订单/物流可接 Mock OMS。
- 返回必须包含 `as_of`；订单和物流必须带状态更新时间。
- 后端从认证上下文注入 `user_id`/`shop_id`，模型不能自行传入这些字段。

### 4.2 通道 B：文档知识 RAG

- 适用于退换货、保修、发票、配送、活动规则、商品说明和 FAQ。
- PostgreSQL 保存文档、版本、生效期、分块和引用元数据；Milvus 保存向量与检索字段。
- 检索必须按店铺、地区、语言、知识库、版本和生效期过滤。
- 回答必须附带 `document_id`、标题、章节/页码、版本、生效日期和片段 ID；证据不足时拒答或转人工。
- 检索片段是不可信数据，不能改变系统规则或工具权限。

### 4.3 通道 C：确定性规则与升级

- 退货资格、退款金额上限、工单状态、风险等级和幂等性由代码/规则引擎决定。
- LLM 只解释规则输出，不能直接批准退款、赔付、优惠券、免单或修改金额。
- `create_return_request` 只创建 `submitted` 申请，不代表退款成功。
- 投诉、法律威胁、人身安全、异常大额订单、连续失败、低置信度、模型与工具冲突和用户要求人工时创建/升级 `handoff_tickets`。
- 写操作必须接收幂等键；同一用户、同一操作、同一键只能成功一次。

### 4.4 横切层

- 认证和租户/店铺范围校验必须在后端和 service/repository 层重复执行。
- 日志必须做 PII 脱敏；不记录完整手机号、地址、身份证、银行卡或订单收件人信息。
- SSE 事件至少区分元信息、增量文本、引用、商品卡片、工具状态、错误和结束事件。
- 所有工具结果使用统一成功/失败信封；失败使用稳定错误码和中文可操作提示。

## 5. 10 类意图与工具映射初稿

以下是最小可测试的分类。后续阶段必须把分类规则、置信度阈值、实体抽取和回退策略写入 `docs/03-architecture.md`、`docs/05-tool-contract.md` 和 `docs/06-api.md`，不能直接在提示词中临时编造工具。

| # | 意图 | 典型问题 | 主路由 | 允许的工具/RAG 路径 | 硬约束 |
|---|---|---|---|---|---|
| 1 | 商品发现 | “预算 300 元内的通勤降噪耳机” | A 结构化 | `search_products` | 预算用整数分；只返回有数据来源的卡片和 `as_of` |
| 2 | 商品详情 | “这款耳机的参数和 SKU 是什么” | A 结构化 | `get_product_detail`，必要时 `check_stock` | 价格、SKU、库存不得来自 RAG 或模型记忆 |
| 3 | 商品比较 | “这两款有什么区别” | A 结构化 | `compare_products`；必要时 `get_product_detail` | 字段对齐；缺失值显式 `unknown` |
| 4 | 价格/库存/优惠 | “现在多少钱、还有货吗、有活动吗” | A 结构化 | `get_product_detail`、`check_stock`、`get_promotion` | 返回 `as_of`；不承诺未生效的活动 |
| 5 | 政策/FAQ/说明 | “七天无理由怎么退” | B RAG | 版本化知识检索 + 引用侧栏 | 必须有引用；按生效期/地区/店铺过滤 |
| 6 | 订单状态 | “我的订单到哪一步了” | A 结构化 | `get_order_status` | 从认证上下文取用户；校验订单归属 |
| 7 | 物流跟踪 | “什么时候送达、物流节点是什么” | A 结构化 | `get_shipment`；必要时 `get_order_status` | 只返回脱敏单号和节点；带更新时间 |
| 8 | 退货/换货 | “这个订单能退吗、帮我申请退货” | C 规则 | `check_return_eligibility` →（用户确认后）`create_return_request` | 先规则判断；写操作需幂等键；只能创建申请 |
| 9 | 投诉/高风险/人工 | “我要投诉、告你们、转人工” | C 升级 | `create_handoff_ticket` | 直接升级；不继续承诺退款/赔偿；记录风险等级 |
| 10 | 闲聊/未知/低置信 | “你好”“这个怎么办”但无足够实体 | 安全回退 | 无写工具；澄清问题、有限 FAQ 检索或转人工 | 不猜测事实；重复失败两次后停止并升级 |

### 5.1 路由优先级

1. 先做安全/高风险检测，再做普通意图分类。
2. 明确要求人工、法律威胁、投诉或异常金额优先进入通道 C。
3. 带商品/订单实体的实时事实问题优先进入通道 A；不能因为命中政策文本就用 RAG 回答价格或库存。
4. 只有政策、规则解释和商品说明书类问题进入通道 B。
5. 分类置信度不足时不强行调用工具，先澄清；仍无法确认时转人工。

## 6. 已识别风险清单

| 级别 | 风险 | 影响 | 后续处理 |
|---|---|---|---|
| 高 | 参考项目无许可证依据 | 复制代码/配置可能造成合规风险 | 仅借鉴思路；不复制 |
| 高 | 参考配置/Compose 含明文凭据 | 泄露风险 | 本项目全部环境变量/占位符 |
| 高 | 参考项目无自动化测试/CI | 无法证明链路稳定 | 本项目从阶段 2 起定义验收标准，阶段 12 做完整测试 |
| 高 | 参考前端接口与后端不一致 | 演示链路可能失效 | 前端统一使用 API 客户端和环境配置 |
| 中 | 参考 Docker 绝对路径、外部网络、bind mount | 跨机器不可复现 | 使用相对路径、named volumes、显式网络和健康检查 |
| 中 | 当前项目 `.gitignore` 不完整 | 误提交 `.env`/构建产物 | 在脚手架/安全阶段修复 |
| 中 | 当前无 `uv.lock` 和测试配置 | 环境与质量不可复现 | 引入依赖时同步锁文件和测试配置 |
| 中 | Docker 端口 6379/8000 已被占用 | 后续 Compose 启动可能冲突 | 启动前只读检查；不得擅自停止容器 |
| 低 | `README.md` 为空、描述占位 | 交付说明不足 | 在部署/演示阶段补全 |
| 低 | 作者邮箱元数据可能保留 | 发布信息不必要暴露 | 发布前由用户确认 |

## 7. 待确认问题

以下问题不在本阶段擅自决定：

1. Milvus standalone 的固定版本是否采用参考项目的 `v2.4.4`，还是采用当前讲义/环境已存在的版本？必须与阶段 4 的 Compose 和兼容性测试一致。
2. Embedding/LLM 的默认 provider 选 Qwen/OpenAI-compatible 还是本地 BGE-M3？测试必须使用 fake provider，真实 provider 只通过环境变量启用。
3. 退货窗口、最终销售商品、运费承担、缺陷/保修等规则以哪份合成政策文档为准？阶段 2 必须定义可测试规则和边界。
4. 管理端与客服工作台在 MVP 中是同一角色入口还是两个权限视图？必须由后端 RBAC/租户边界决定。
5. 当前已有 Redis/Milvus 容器和端口占用是否保留给本项目使用？阶段 4 启动前需用户确认，不得自动停止或删除。
6. 是否需要把参考项目中的 FAQ/BM25 作为本项目 MVP 的必需能力，还是先以 PostgreSQL 检索 + Milvus RAG 为基线并在评测后决定？

## 8. 阶段 1 审计结论

- 当前项目是可安全扩展的空白脚手架，但尚无可运行后端、前端、数据库或测试。
- 参考 `Itcast_qa_system` 的模块划分和 RAG 分层可提供思路，但其许可证无法确认，且存在工程与安全缺陷，不能复制。
- 参考项目不具备可证明的自动化测试/CI；不能把课程演示或压测脚本当作验收证据。
- ShopMate 后续必须围绕结构化事实、政策引用、确定性规则、权限和可审计写入建立三通道边界。
- 阶段 2 未开始；本文件不定义最终 PRD 或实现细节。

## 9. 验收对照

| 验收项 | 结果 | 证据 |
|---|---|---|
| 参考项目结构、技术栈、模块、测试、Docker 方式已记录 | 通过 | 第 3 节 |
| 密钥、路径写死、缺失依赖和合同冲突已记录 | 通过 | 第 2、3、6 节 |
| 三通道架构初稿已记录 | 通过 | 第 4 节 |
| 10 类意图与工具映射已记录 | 通过 | 第 5 节 |
| 风险与待确认问题已记录 | 通过 | 第 6、7 节 |
| 未修改参考目录/业务代码/容器/Git | 通过 | 只读命令和仅文档写入 |
