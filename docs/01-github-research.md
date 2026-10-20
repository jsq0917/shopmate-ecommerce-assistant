# GitHub 参考仓库许可证与可借鉴模块调研

> 阶段：阶段 1 — 只读审计与 GitHub 调研  
> 调研日期：2026-10-18（Asia/Shanghai）  
> 结论性质：技术调研，不构成法律意见。所有仓库均未 clone、未执行、未复制代码、配置或数据。

## 1. 核验方法

本次通过 GitHub REST API 和仓库页面只读核验：

1. `GET /repos/{owner}/{repo}`：仓库 URL、默认分支、主语言、是否归档、API 识别许可证。
2. `GET /repos/{owner}/{repo}/commits/{default_branch}`：最新 commit SHA、提交日期和标题。
3. `GET /repos/{owner}/{repo}/license`：许可证路径、SPDX 标识、LICENSE blob SHA 和内容首段。
4. `GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1`：目录、测试、CI、Docker 和关键源码路径。
5. 对 README 断言与代码/测试文件分开记录；未把 README 自报指标当成本项目实测结果。

许可证核验原则：

- SPDX 由 GitHub License API 返回，不凭 README badge 或项目名称猜测。
- 同时记录 LICENSE 文件的 commit-pinned URL 与 Git blob SHA，便于复查具体版本。
- “允许使用”不等于“可以不署名复制”。本项目优先只借鉴架构、接口和测试思路，不直接复制源码。

## 2. 元数据与许可证总表

| 仓库 | 默认分支 | 主语言 | 最新 commit | Commit 日期（UTC） | SPDX | LICENSE 证据 |
|---|---|---|---|---|---|---|
| [LaelaZorana/ecom-support-copilot](https://github.com/LaelaZorana/ecom-support-copilot) | `main` | Python | `058c8bc3101655ecd90d65d12f9b1534667f1917` | `2026-08-30T07:48:10Z` | MIT | [LICENSE](https://github.com/LaelaZorana/ecom-support-copilot/blob/058c8bc3101655ecd90d65d12f9b1534667f1917/LICENSE)，blob SHA `a2b1c3970fd7c78837751fed41b11e341e057d25` |
| [auron-lmh/rag-ecommerce-customer-service](https://github.com/auron-lmh/rag-ecommerce-customer-service) | `master` | Python | `1f8c845a3a76b241598766dbe6a62ac2da374049` | `2026-08-14T09:19:36Z` | MIT | [LICENSE](https://github.com/auron-lmh/rag-ecommerce-customer-service/blob/1f8c845a3a76b241598766dbe6a62ac2da374049/LICENSE)，blob SHA `c4a8d96f9b647f300339ee1fe5e63a8af04b88a1` |
| [RyanCoreAI/spring-ai-crossborder-customer-service](https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service) | `master` | Java | `1e5b8d4c4d9f139eebf09d66965e5fc626c91326` | `2026-07-13T05:50:34Z` | MIT | [LICENSE](https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service/blob/1e5b8d4c4d9f139eebf09d66965e5fc626c91326/LICENSE)，blob SHA `3f48b5d8f584e4d79525de3c4742be6efacd6947` |
| [officialayush23/DAKSHA](https://github.com/officialayush23/DAKSHA) | `main` | JavaScript | `c135f3bab14efee700b0b526b41032bbb293ed9e` | `2026-10-04T11:48:06Z` | Apache-2.0 | [LICENSE](https://github.com/officialayush23/DAKSHA/blob/c135f3bab14efee700b0b526b41032bbb293ed9e/LICENSE)，blob SHA `b09cd7856d58590578ee1a4f3ad45d1310a97f87` |

Commit 链接：

- [ecom-support-copilot commit](https://github.com/LaelaZorana/ecom-support-copilot/commit/058c8bc3101655ecd90d65d12f9b1534667f1917) — `Run tests on a 3.10 to 3.12 matrix and add a container smoke test job`
- [rag-ecommerce-customer-service commit](https://github.com/auron-lmh/rag-ecommerce-customer-service/commit/1f8c845a3a76b241598766dbe6a62ac2da374049) — `feat(RAG): 检索质量进阶 — 语义分块中文修复 + Overlap + RRF + 父文档检索 + 同义词 + 评测门禁`
- [spring-ai-crossborder-customer-service commit](https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service/commit/1e5b8d4c4d9f139eebf09d66965e5fc626c91326) — `docs: refresh readme demo with latest runtime screens`
- [DAKSHA commit](https://github.com/officialayush23/DAKSHA/commit/c135f3bab14efee700b0b526b41032bbb293ed9e) — `Benchmarks, stricter tool schemas, global action budget`

## 3. LaelaZorana/ecom-support-copilot

### 3.1 许可证依据

- 仓库：https://github.com/LaelaZorana/ecom-support-copilot
- 默认分支：`main`
- 最新 commit：`058c8bc3101655ecd90d65d12f9b1534667f1917`（`2026-08-30T07:48:10Z`）
- GitHub License API：`license.spdx_id = MIT`，名称 `MIT License`
- LICENSE 文件：`LICENSE`
- LICENSE commit-pinned URL：https://github.com/LaelaZorana/ecom-support-copilot/blob/058c8bc3101655ecd90d65d12f9b1534667f1917/LICENSE
- LICENSE blob SHA：`a2b1c3970fd7c78837751fed41b11e341e057d25`
- 内容首段确认：`MIT License`，`Copyright (c) 2026 Laela Zorana`

### 3.2 已观察证据

| 结论 | 证据 | 证据等级 |
|---|---|---|
| 提供引用式客服、Mock Orders、确定性退款规则、低置信度转人工 | `README.md` 第 25–47 行；`supportcopilot/agent.py` 顶部说明 | README + 代码注释 |
| 退款规则按政策分支决定，并有 pytest 覆盖 | `supportcopilot/refunds.py`；`tests/test_refunds.py` | 代码 + 测试文件 |
| 检索置信度可用于升级判断 | `supportcopilot/retrieval.py` 的 confidence 注释与 `tests/test_retrieval.py` | 代码 + 测试文件 |
| CI 覆盖 Python 3.10–3.12、pytest 和容器健康检查 | `.github/workflows/ci.yml` | CI 文件 |
| 有 Dockerfile 和 Compose | 根目录 `Dockerfile`、`docker-compose.yml` | 仓库树 |

### 3.3 可借鉴项

- RAG 回答附引用，结构化订单事实走 Mock Orders，不让模型凭记忆编造。
- 退款判断用确定性规则，并把规则判断与自然语言解释分开。
- 低置信度或敏感场景升级人工。
- 测试按检索、退款规则、Agent 路由、指标和 Web 层拆分。
- CI 同时运行单元测试与容器 smoke test。

### 3.4 禁止直接复制的项

- 不复制其业务数据、seed 工单、具体政策文本或页面资产。
- 不把 README 的 `80% (16/20)` deflection、ROI 或成本数字作为 ShopMate 结果；这些是该仓库基于 20 条 seed 工单的自报数据。
- 不复制其 TF-IDF/纯 Python fallback 作为 ShopMate 默认检索架构；ShopMate 使用 PostgreSQL + Milvus 的合同方案。
- 不直接复制代码；如果未来确需复用，必须保留 MIT 许可证与版权声明，并单独记录具体文件和来源 commit。

### 3.5 许可证义务结论

MIT 许可证允许使用、复制、修改、合并、发布、分发、再许可和销售，但任何复制或实质性使用必须保留版权声明和许可声明；软件按“无担保”提供。本项目当前选择“只借鉴设计，不复制代码”。

## 4. auron-lmh/rag-ecommerce-customer-service

### 4.1 许可证依据

- 仓库：https://github.com/auron-lmh/rag-ecommerce-customer-service
- 默认分支：`master`
- 最新 commit：`1f8c845a3a76b241598766dbe6a62ac2da374049`（`2026-08-14T09:19:36Z`）
- GitHub License API：`license.spdx_id = MIT`，名称 `MIT License`
- LICENSE 文件：`LICENSE`
- LICENSE commit-pinned URL：https://github.com/auron-lmh/rag-ecommerce-customer-service/blob/1f8c845a3a76b241598766dbe6a62ac2da374049/LICENSE
- LICENSE blob SHA：`c4a8d96f9b647f300339ee1fe5e63a8af04b88a1`
- 内容首段确认：`MIT License`，`Copyright (c) 2026 Liang Minghuang`

### 4.2 已观察证据

| 结论 | 证据 | 证据等级 |
|---|---|---|
| HEAD 的检索路径将 dense 与 sparse 分开召回后做 RRF | `src/embedding/retriever.py` 的 `_rrf_fusion()` 和 `search()` | 代码 |
| README 的融合策略说明存在滞后/不一致 | README 仍展示 `WeightedRanker`，而 HEAD `retriever.py` 已调用 RRF | 文档与代码对照 |
| 订单查询包含用户归属校验 | `src/orders/order_service.py` 的 `query_order(..., user_id, is_admin)` 注释与分支 | 代码 |
| 有退款/退货规则测试、访问控制测试 | `tests/business/test_return_policy.py`、`tests/api/test_access_control.py` | 测试文件 |
| 有 RAG 评测指标与门禁脚本 | `src/evaluation/metrics.py`、`scripts/eval_gate.py` | 代码 |
| CI 运行 pytest；Milvus 与 RAG 使用拆分 Compose | `.github/workflows/ci.yml`、`docker-compose-milvus.yml`、`docker-compose-rag.yml` | CI/Compose 文件 |
| 有转人工、承诺护栏、PII 和权限相关模块目录 | `src/engineering/promise_guard.py`、`src/engineering/pii_redactor.py`、`src/engineering/security.py`、测试目录 | 仓库树 |

### 4.3 可借鉴项

- dense + sparse 分别召回后做 RRF；用可解释的倒数排名融合替代不可解释的固定权重。
- 子块召回后补全父文档上下文，并保留来源。
- 订单查询从认证上下文获取用户身份并校验归属。
- 对退款/退货规则、权限和 RAG 指标分别建立测试与门禁。
- 用健康检查、服务依赖和拆分 Compose 管理 Milvus/RAG。

### 4.4 禁止直接复制的项

- 不复制 README 的 Recall@5、MRR、Faithfulness 等 49 条样本结果；它们是该仓库自身评测数据，不是 ShopMate 实测。
- 不复制其订单数据库、真实/大体量订单数据或其他项目的业务数据。
- 不直接采用其 13 节点 LangGraph 编排或多层策略全集；ShopMate MVP 是单 Agent + 确定性工具。
- 不直接复制源码；如未来复用，必须保留 MIT 版权与许可声明，并记录文件、commit 和修改。

### 4.5 许可证义务结论

MIT 允许广泛的商业和非商业使用、修改与分发，但复制时必须保留版权与许可声明；不提供担保。文档中的“✅”功能、评测数字和部署状态不能替代 ShopMate 自测。

## 5. RyanCoreAI/spring-ai-crossborder-customer-service

### 5.1 许可证依据

- 仓库：https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service
- 默认分支：`master`
- 最新 commit：`1e5b8d4c4d9f139eebf09d66965e5fc626c91326`（`2026-07-13T05:50:34Z`）
- GitHub License API：`license.spdx_id = MIT`，名称 `MIT License`
- LICENSE 文件：`LICENSE`
- LICENSE commit-pinned URL：https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service/blob/1e5b8d4c4d9f139eebf09d66965e5fc626c91326/LICENSE
- LICENSE blob SHA：`3f48b5d8f584e4d79525de3c4742be6efacd6947`
- 内容首段确认：`MIT License`，`Copyright (c) 2026 RyanCoreAI`

### 5.2 已观察证据

| 结论 | 证据 | 证据等级 |
|---|---|---|
| 是 Java 多模块后端 + Web 前端工程 | 根 `pom.xml`；`omni-merchant-*` 模块目录；`omnimerchant-web/` | 仓库树 |
| 有后端 Java 测试、CI 和 CodeQL 工作流 | `omni-merchant-agent/src/test/java/...`；`.github/workflows/ci.yml`；`.github/workflows/codeql.yml` | 测试/CI 文件 |
| 有 Dockerfile、Compose demo/prod 配置 | 根 `Dockerfile`、`docker-compose.yml`、`compose.demo.yml`、`compose.prod.yml` | 仓库树 |
| README 描述订单工具、升级/人工接管、租户隔离、审批和引用 | README 的架构与功能说明；`omni-merchant-tenant/`、`omni-merchant-agent/`、`omni-merchant-knowledge/` 目录 | README + 仓库树 |
| README 描述 BM25 + Vector + RRF、citation 和 deterministic eval | README 的 AI/RAG 与评测章节 | README 自述，未逐行执行代码验证 |

### 5.3 可借鉴项

- 模型提出工具调用请求，应用层统一做 tenant、role、identity、risk 和 approval 校验。
- 高风险动作进入审批，而不是由模型直接执行。
- 订单/物流工具与知识检索分层；引用和证据充分性单独评估。
- 客服工作台、管理端、租户隔离和审计是产品级能力，不应只做聊天窗口。
- 用 CI、CodeQL、数据库迁移、健康检查和 Docker Compose 形成工程闭环。

### 5.4 禁止直接复制的项

- 不把 Java/Spring AI 架构迁移到 ShopMate；本项目固定 Python/FastAPI。
- 不引入其多模块企业级复杂度、复杂 Agent 编排或跨租户基础设施作为 MVP 前置条件。
- 不复制 README 的 102/102、Tool Precision、Citation Coverage 等自报指标；这些是参考仓库环境和数据集的结果。
- 不复制真实商户配置、支付/渠道凭据或业务数据。
- 如未来复用任何 MIT 代码，必须保留版权与许可声明并记录来源 commit。

### 5.5 许可证义务结论

MIT 允许使用、修改和分发，但必须保留版权和许可声明；不提供担保。其产品截图、演示数据和品牌资产不因 MIT 自动成为可随意复用的素材。

## 6. officialayush23/DAKSHA

### 6.1 许可证依据

- 仓库：https://github.com/officialayush23/DAKSHA
- 默认分支：`main`
- 最新 commit：`c135f3bab14efee700b0b526b41032bbb293ed9e`（`2026-10-04T11:48:06Z`）
- GitHub License API：`license.spdx_id = Apache-2.0`，名称 `Apache License 2.0`
- LICENSE 文件：`LICENSE`
- LICENSE commit-pinned URL：https://github.com/officialayush23/DAKSHA/blob/c135f3bab14efee700b0b526b41032bbb293ed9e/LICENSE
- LICENSE blob SHA：`b09cd7856d58590578ee1a4f3ad45d1310a97f87`
- 内容首段确认：`Apache License Version 2.0, January 2004`

### 6.2 已观察证据

| 结论 | 证据 | 证据等级 |
|---|---|---|
| FastAPI 后端 + React 前端 + LangGraph 多 Agent 商城 | README 的 What it is / Tech stack；`BACKEND/app/agentic/`、`daksha-frontend/` | README + 仓库树 |
| README 声称工具身份由引擎注入，金额不是模型参数 | README 的 Identity binding 说明；`BACKEND/app/core/auth.py`、`deps.py` | README + 部分代码 |
| 有 policy gate、human approval、tool registry、commerce tools 目录 | `BACKEND/app/agentic/commerce/policies.py`、`tools.py`、`core/graph.py`、`core/registry.py` | 仓库树 |
| 最新 commit 说明加强工具 schema 和全局 action budget | Commit message 与仓库树中的 `BACKEND/tests/test_engine_core.py` | Commit + 测试路径 |
| 观察到的 CI 证据有限 | 仓库树未发现 `.github/workflows`；测试抽样仅有 `BACKEND/tests/test_engine_core.py` | 仓库树 |
| 未观察到根 Dockerfile/Compose 路径 | 递归树中未匹配到 Dockerfile/Compose；README 部署说明依赖外部服务 | 仓库树 + README |

### 6.3 可借鉴项

- 工具 schema 拒绝未知字段，防止模型注入 `user_id`、`price` 等敏感参数。
- 引擎从认证上下文注入身份；金额和总价在服务端计算。
- 在工具执行前运行 policy gate，高风险动作进入人工审批。
- 为整个 Agent 轮次设置 action budget，避免循环调用。
- 把商品、订单、退货、客服和人工接管视为同一业务状态机的一部分。

### 6.4 禁止直接复制的项

- 不复制多 Agent supervisor/handoff 架构；ShopMate MVP 明确采用单 Agent + 确定性工具。
- 不复制支付、结算、优惠券发放等超出 MVP/业务铁律的功能。
- 不复制其 Supabase、支付、Telegram 或第三方渠道配置/凭据。
- 不把其 benchmark 或 README 指标当作 ShopMate 结果。
- 不直接复制代码；如未来复用 Apache-2.0 代码，必须保留许可证、变更说明、适用的 NOTICE 内容，并遵守商标与专利条款。

### 6.5 许可证义务结论

Apache-2.0 允许商业使用、修改、分发和专利授权，但复制/分发时需要提供许可证副本、标明修改，并保留适用的 NOTICE 和归属信息；不得暗示获得商标许可。任何实际代码复用都应在后续阶段单独做许可证合规审查。

## 7. 跨仓库结论

1. 四个仓库均有可确认的宽松许可证：三个 MIT、一个 Apache-2.0。许可证结论只针对上述 commit 的 LICENSE 文件，不对未来版本作保证。
2. 本项目当前不复制四个仓库的源码，只借鉴以下稳定模式：
   - 结构化工具与 RAG 分离；
   - 政策引用、订单归属和确定性退款规则；
   - 身份注入、工具 schema、policy gate 和人工升级；
   - CI、测试分层和容器 smoke test。
3. 所有 README 中的业务收益、检索分数和覆盖率都是参考仓库自报结果，不能直接迁移为 ShopMate 的简历或演示数字。
4. 参考仓库的工程规模不作为 ShopMate 的目标；ShopMate 按本项目合同保持模块化单体、单 Agent 和可测试的确定性工具层。
5. 若未来需要复制任何代码，必须先在独立清单中记录仓库 URL、commit、文件路径、许可证、版权声明和修改内容，并由用户确认。

## 8. 许可证依据索引

| 仓库 | SPDX | 许可证文件 | Blob SHA |
|---|---|---|---|
| `LaelaZorana/ecom-support-copilot` | MIT | https://github.com/LaelaZorana/ecom-support-copilot/blob/058c8bc3101655ecd90d65d12f9b1534667f1917/LICENSE | `a2b1c3970fd7c78837751fed41b11e341e057d25` |
| `auron-lmh/rag-ecommerce-customer-service` | MIT | https://github.com/auron-lmh/rag-ecommerce-customer-service/blob/1f8c845a3a76b241598766dbe6a62ac2da374049/LICENSE | `c4a8d96f9b647f300339ee1fe5e63a8af04b88a1` |
| `RyanCoreAI/spring-ai-crossborder-customer-service` | MIT | https://github.com/RyanCoreAI/spring-ai-crossborder-customer-service/blob/1e5b8d4c4d9f139eebf09d66965e5fc626c91326/LICENSE | `3f48b5d8f584e4d79525de3c4742be6efacd6947` |
| `officialayush23/DAKSHA` | Apache-2.0 | https://github.com/officialayush23/DAKSHA/blob/c135f3bab14efee700b0b526b41032bbb293ed9e/LICENSE | `b09cd7856d58590578ee1a4f3ad45d1310a97f87` |

## 9. 阶段验收对照

| 验收项 | 结果 | 证据 |
|---|---|---|
| 每个仓库记录 URL、默认分支、最新 commit | 通过 | 第 2 节总表及 commit 链接 |
| 每个仓库记录 SPDX、LICENSE 路径、blob SHA | 通过 | 第 2、3–6、8 节 |
| 可借鉴模块与禁止复制项分别记录 | 通过 | 第 3–6 节 |
| 未 clone、执行或复制参考仓库 | 通过 | 仅使用 GitHub API/只读元数据 |
| 未把 README 数字当作本项目实测 | 通过 | 第 7 节 |
