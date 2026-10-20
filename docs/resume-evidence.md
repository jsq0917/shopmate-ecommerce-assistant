# 简历与面试证据台账

> 版本：2026-10-20（阶段 15：简历证据与面试材料）
> 依据：`AGENTS.md` §21（完成报告）、§22（简历与面试证据规则）、§17（评估与性能）
> 配套文档：[`interview-prep.md`](interview-prep.md)（中文项目描述 + 面试问答提纲）

## 0. 先说三条硬约束

1. **本仓库当前 0 个 commit**（`git log` 返回 `your current branch 'main' does not have any commits yet`）。
   因此无法提供 commit SHA 作为证据，所有结论只能以**文件 + 可复现命令 + 命令输出**为准。
   若需要 commit 级追溯，须由项目所有者先授权提交。
2. **本文件只记录本仓库实测结果**。课程场景里的 82% / 42% / 70% / 18% 是示例宣传值
   （`AGENTS.md` §2.3），四个 GitHub 参考仓库的工作也不属于本项目（§19），两者**都不得**出现在简历里。
3. **没有量化数据的一律写定性**。本文件第 4 节每一行都带"限制与口径"，第 5 节明确区分
   「已实现」「已测试但有已知缺陷」「未实现/计划中」——后者不得写成已完成。

---

## 1. 本人负责的边界（避免把别人的工作写成自己的）

| 内容 | 归属 | 依据 |
|---|---|---|
| `src/`、`frontend/`、`web/`、`scripts/`、`alembic/`、`compose*.yaml`、`docs/` 下的全部实现与文档 | 本项目产出（本人执行） | 目录清单；`docs/project-status.md` 各阶段记录 |
| 课程资料 `E:\AI大模型开发\eduRAG(陈杰老师)` | 只读参考，**未纳入本项目** | `AGENTS.md` §0.5、§2 |
| 四个 GitHub 参考仓库（ecom-support-copilot、rag-ecommerce-customer-service、spring-ai-crossborder、DAKSHA） | 仅借鉴架构与接口思路，**未复制源码** | `docs/01-github-research.md`（URL + commit + license） |
| 课程场景 HTML 中的业务指标 | 示例宣传值，**不是实测** | `AGENTS.md` §2.3 |

一句话边界表述（面试可直接用）：
> "架构思路参考了公开项目和课程资料，但代码、数据、评测脚本和指标都是我在本仓库自己实现、自己跑出来的；
> 参考项目 README 里的任何数字我都没有引用。"

---

## 2. 项目定位（一句话 + 三个可验证特征）

**一句话**：ShopMate 是可追溯的电商智能客服与轻导购助手——结构化事实只来自 PostgreSQL，
政策回答必须带引用，退款/赔付由确定性规则和人工决定，模型只负责解释。

三个可验证特征：

1. **三条路径分流**：结构化（商品/订单/物流）→ PostgreSQL；知识（政策/FAQ）→ Milvus + PG 元数据；
   确定性（退货资格/转人工）→ 代码规则。三条路径在 `src/.../agents/router.py` 中各有入口，
   并有 10 类意图枚举与 `AGENTS.md` §10.7 对应。
2. **检索链路单模型双输出**：本地 BGE-M3 一次前向产出 dense(1024, L2 归一化) + sparse lexical weights，
   Milvus `hybrid_search` 各取 top 30、RRF(k=60) 融合，随后用 PostgreSQL 二次复核
   （店铺/知识库/地区/语言/版本/生效期），最后 4–8 片段 + 稳定引用 ID。
   任一路失败报错，**不静默降级为 dense-only**（`rag/retrieval.py` 模块 docstring 与 `RetrievalMode`）。
3. **写操作幂等 + 归属校验**：退货申请、转人工工单都要求 `idempotency_key`，
   重复提交返回同一条记录（`db/repositories/idempotency.py`）；订单/物流/退货/工单全部从认证上下文取
   `user_id` + `shop_id`，不信任前端传参。

---

## 3. 本次（2026-10-20）复核过的命令与输出

> 下表是写这份台账时**亲自跑过**的命令，不是从旧报告抄的。旧报告数字与本轮不一致处已标注。

| 命令 | 输出（原文摘要） | 结论 |
|---|---|---|
| `uv run ruff check .` | `All checks passed!` | 静态检查通过 |
| `uv run pytest -q` | `600 passed, 2 skipped, 26 warnings in 138.41s` | 收集 602，跳过 2 条为真实 BGE-M3 模型测试（需 `SHOPMATE_RUN_MODEL_TESTS=1`） |
| `uv run pytest tests/security -q` | `86 passed, 8 warnings in 3.42s` | 安全子集全绿 |
| `cd frontend && npx vitest --run` | `Test Files 14 passed (14) / Tests 124 passed (124)` | 组件测试全绿 |
| `cd frontend && npm run typecheck` | 无输出（`vue-tsc --noEmit` 0 错误） | 类型检查通过 |
| `uv run python scripts/verify_stage13.py` | `全部一致（独立复算 == 原始结果）` | 头条指标可从 records 复算 |
| `uv run python scripts/check_deploy_security.py` | `合计 34 项：PASS 34 / WARN 0 / FAIL 0` | 部署安全静态复查通过 |
| `wc -l` / `sha256sum` 数据集 | `136` / `7606cfce…`；`58` / `856f3338…` | 与报告 2.1、原始结果 `datasets` 三方一致 |
| `grep Aggregated locust-stage13-u20/u40_stats.csv` | `1350 / 0 失败 / 23.0833 req/s`；`1762 / 2 失败 / 29.6058 req/s` | 压测取数口径正确 |
| `git log --oneline` | `your current branch 'main' does not have any commits yet` | 仓库无 commit，见 §0.1 |

**测试数量的口径对账（避免"数字变了"的困惑）**：
`591`（阶段 14 首次记录）= `587`（阶段 12 基线）+ `4`（Host 白名单首版）。
之后 22.7.2 整改把 Host 白名单单测从 4 条扩到 **9** 条、并新增 **4** 条生产密钥校验单测，
因此当前是 `587 + 9 + 4 = 600 passed`。本轮实测 600，两张单测文件分别有 9 / 4 个 `def test_`。

---

## 4. 量化指标证据表（每个数字都能追溯）

> 全部来自同一次运行 `data/eval/results/stage13-20261020T013230Z.json`，
> 可由 `uv run python scripts/verify_stage13.py` 逐项复算（不一致则退出码 1）。
> "限制与口径"一列是**必须与数字一起说**的内容，单独引用数字视为误用。

### 4.1 检索质量（58 条金标，50 条有金标文档）

| 指标 | 数值 | 数据集 / 样本 | 命令或文件 | 限制与口径 |
|---|---|---|---|---|
| Recall@1 / @3 / @5 / @10 | **1.00 / 1.00 / 1.00 / 1.00** | 58 条金标，分母 50（有金标文档） | `scripts/verify_stage13.py`；报告 2.4.1 | 语料仅 **27 条有效向量**（Milvus `count(*)` 28，含 1 条孤儿；21 个 ready 版本），**已饱和，不可外推到万级知识库** |
| MRR@10 | **1.00** | 同上 | 同上 | 同上 |
| context precision | **0.8459** | 50 | 同上 | 自建 RAGAS 同构实现（金标代替 LLM 判定），非官方 ragas 包 |
| context recall | **1.00** | 50 | 同上 | 用 `expected_phrases` 短语法，非语义覆盖 |
| 主引用正确率 | **1.00** | 期望可答案例 | 同上 | 严格口径：第一条引用标题必须命中金标 |
| chunk 级引用精度 | **0.2664 → 0.3090（+16.0% 相对）** | 58 | 同上（baseline vs optimised） | 4–8 片段必然稀释；这是**上下文稀释改善**，不是排序变好、不是业务收益 |
| 平均选取片段数 | **6.22 → 5.03（−19.1%）** | 58 | 同上 | 优化只改了配置（`retrieval_max_chunks` 8→6），没改业务规则 |
| 检索行为正确率 | **0.9828**（误答 0 / 误拒 1） | 58 | 同上 | 唯一误拒 `exact-05`（相似度 0.6142 < 门槛 0.62），属阈值边界 |
| 双路 vs dense-only | **无差异**（R@1、MRR、ctxP、行为正确率全部相同） | 58 | 报告 2.4.3 | **禁止写"混合检索提升召回/准确率"**；稀疏支路保留理由是契约要求 + 精确词鲁棒性 |
| 证据门槛 | **0.62** | dev 29 条标定 / test 29 条复测 | 报告 2.4.5 | dev/test 各 29 条，单条用例约 3.4 个百分点；只作量级参考；test 上 0.60 略好但**未采用**（避免"调到赢"） |

### 4.2 业务与安全（136 条，真实调用 `ChatService` + 真实工具 + 真实 PG）

| 指标 | 数值 | 数据集 / 样本 | 命令或文件 | 限制与口径 |
|---|---|---|---|---|
| 意图准确率 | **0.7059（96/136）** | 136 | `verify_stage13.py`；报告 2.6 | 路由是关键词加权规则，长尾政策表述漏判；`multi_turn` 的 +1 来自数据集 `history` 重建，不是系统改动 |
| 工具选择准确率 | **0.6691（91/136）** | 136 | 同上 | `PRODUCT_FACT` 被并到搜索分支，与 §9.1 契约不一致（9 条） |
| 任务成功率 | **0.6324（86/136）** | 136 | 同上 | 安全类按"无泄漏且无写副作用"判 |
| 严格拒答率 | **0.00（0/7）** | 7 条 `no_answer` | 同上 | **这是硬伤，必须写**：7 条无依据问题没有一条走到固定拒答文案 |
| 不编造率（宽松） | **0.5714（4/7）** | 7 | 同上 | 拒答或澄清都算"未编造" |
| 越权拦截率 | **1.00（8/8）** | 8 条带 `authorization` 标签 | 同上；分母 `authorization_cases=8` 写入原始结果 | 分母仅 8 条，样本小；跨店铺 admin 运行时用例仍未构造 |
| 转人工召回 / 精确率 | **0.8182（9/11）/ 1.00（9/9）** | 11 条应升级 | 同上 | 漏判 2 条：`eval-089`（账号被盗）、`eval-121` |
| Prompt injection 安全率 | **1.00（11/11）** | 11 条注入用例 | 同上 | 用例由本项目编写，覆盖有限 |
| 业务链路泄漏用例 | **0** | 136 | 同上 | 系统提示词 / 连接串 / API Key / 他人订单号 |
| 错误轮 | **0** | 136 | 同上 | 无 5xx、无未捕获异常 |

### 4.3 生成质量（分两条路径，不可混为一谈）

| 指标 | 数值 | 数据集 / 样本 | 命令或文件 | 限制与口径 |
|---|---|---|---|---|
| faithfulness（结构化路径，确定性代理） | **0.8318** | 107 轮 | 报告 2.5.1 | 句中数字必须能在工具卡片/引用/用户原话中找到；**不是** RAGAS；未逐轮落盘，需重跑脚本 |
| answer relevancy（结构化路径，代理） | **0.5937** | 107 轮 | 同上 | BGE-M3 余弦，**不是** RAGAS 逆问题生成 |
| 政策答案 status 分布 | **answered 5 / handoff 4 / refused 27** | 36 条政策用例 | `verify_stage13.py` | 本地 `qwen2.5:7b`，不代表云端强模型 |
| 可答用例应答率 | **0.1724（5/29）** | 29 条期望可答 | 同上 | 20 条"有证据仍拒答"是模型过度保守，不是检索失败 |
| 无答案用例正确拒答 | **1.00（7/7）** | 7 | 同上 | 与 4.2 的严格拒答 0/7 不矛盾：这里直接调 `PolicyQAService`，绕过了意图路由 |
| 引用合规率 | **1.00（5/5）** | 5 条 answered | 同上 | 只用了提供的 `[cN]` |
| faithfulness（LLM 判定） | **0.88** | 5 条 answered | 同上 | 剔除 2 条哨兵泄漏后为 0.9333（3 条）；judge 与被测模型同族，存在自偏好偏差 |
| answer relevancy（LLM 判定） | **0.52** | 5 条 answered | 同上 | 同上；**不能**写成"政策问答准确率 88%" |
| token / 成本 | **77,709 tokens / 0 USD** | 生成 72,500 + judge 5,209 | 同上 | **本地推理零费用**，不能据此推云上成本比例 |

### 4.4 工程与容量

| 指标 | 数值 | 数据集 / 样本 | 命令或文件 | 限制与口径 |
|---|---|---|---|---|
| 聊天轮延迟 P50 / P95 | **25.63 / 43.10 ms** | n=109（`latency_kind=chat_turn`） | `verify_stage13.py` | 路由 + 工具 + 确定性回答；单机 CPU |
| 政策检索轮延迟 P50 / P95 | **153.61 / 202.32 ms** | n=18（`policy_retrieval`） | 同上 | 仅 BGE-M3 编码 + 双路检索，无生成；约 130 ms 是 CPU 编码 |
| SSE 首 token P50 / P95 | **24.99 / 42.39 ms** | n=107 | 同上 | 逐条 record 落盘 `first_delta_ms`，可复算 |
| 政策答案（7B）延迟 P50 / P95 | **1373.22 / 2936.89 ms** | n=36 | 同上 | 本地 Ollama，单机 CPU |
| 检索评测延迟 P50 / P95 | **147.20 / 192.08 ms** | 58 次 | 同上 | baseline_hybrid 单次检索 |
| 压测吞吐 | **23.08 → 29.61 req/s（+28.3%）** | 20u / 40u，各 60s | CSV `Aggregated` 行 `Requests/s` | 并发翻倍 P95 570→2400 ms，**已饱和**；不能当生产容量 |
| 压测失败 | 20u: **0/1350**；40u: **2/1762（0.11%）** | 同上 | 同上 | 2 条 `RemoteDisconnected`，连接层抖动 |
| 索引规模 | PG **48** chunk 行 / **32** 内容哈希 / **21** ready 版本；Milvus `count(*)` **28**，PG↔Milvus 交集 **27**，**孤儿 1** 条 | 1 个店铺 | 原始结果 `index` 快照 | 两个口径都对但含义不同；21 行 PG chunk 未索引，属索引卫生问题 |
| 后端规模 | **113** 个 `.py` / **22,751** 行（`src/`） | — | `find` + `wc -l` | 含合成数据生成器，不等于业务代码量 |
| 前端规模 | **31** 个 `.vue`；`src` 下 ts+vue 共 **8,901** 行 | — | 同上 | — |

### 4.5 质量门禁

| 门禁 | 数值 | 命令 | 限制 |
|---|---|---|---|
| 后端测试 | **600 passed, 2 skipped**（收集 602，138.41s） | `uv run pytest -q` | 2 条 skip 需真实 BGE-M3 权重；阶段 12 曾在 `SHOPMATE_RUN_MODEL_TESTS=1` 下实测 2 passed |
| 安全测试 | **86 passed** | `uv run pytest tests/security -q` | 矩阵覆盖 SEC-01–19，其中 2 项因路由未注册无法验证 |
| 前端组件测试 | **124 passed / 14 files** | `npx vitest --run` | — |
| 前端类型检查 | **0 错误** | `npm run typecheck` | strict 模式 |
| E2E（Playwright） | **16 用例 / 16 passed** | 见 `docs/test-report.md` §2.2 | **本轮未复跑**（需先起 API + 前端）；用例数可由 `grep -c "test("` 核对为 16 |
| 部署安全复查 | **34 PASS / 0 WARN / 0 FAIL** | `uv run python scripts/check_deploy_security.py` | 静态检查，不等于渗透测试 |
| 生产编排校验 | 两份 `config --quiet` 退出码 0 | `docker compose [-f compose.prod.yaml] config --quiet` | 本轮未复跑（未启容器） |
| 评测复算 | **0 不一致项** | `uv run python scripts/verify_stage13.py` | 独立实现，不 import 评测脚本 |

---

## 5. 实现状态三分（写简历时按这一张表选词）

### 5.1 已实现且已测试（可以写"实现了"，并给出证据）

| 能力 | 关键文件 | 证据 |
|---|---|---|
| 商品搜索 / 详情 / 比较 / 库存（4 个只读工具） | `domain/catalog/*`、`db/repositories/catalog.py`、`tools/catalog_tools.py` | `tests/unit/test_catalog_*.py`、`tests/integration/test_catalog_*.py` |
| 政策 RAG：BGE-M3 双向量 + hybrid + RRF + PG 复核 + 引用 + 无证据拒答 | `rag/{embeddings,retrieval,milvus_store,citations,policy_qa}.py` | `tests/unit/test_retrieval.py`、`test_policy_qa.py`、`test_citations.py`、`tests/integration/test_milvus_store.py`、`scripts/verify_stage13.py` |
| 10 类意图路由 + 查询改写 + FAQ 缓存 | `agents/router.py`、`rag/query_rewrite.py`、`rag/faq.py` | `tests/unit/test_intent_router.py`（56）、`test_query_rewrite.py`（22）、`test_faq_cache.py`（31） |
| 输入/输出护栏、PII 脱敏、风险判定 | `safety/{input_guard,output_guard,pii,risk}.py` | `tests/security/test_input_guard.py`（34）、`test_output_guard.py`（19）、`test_risk_handoff.py`（20）、`test_pii.py`（21） |
| 订单 / 物流 / 退货资格 / 退货申请 / 转人工（5 个工具，含幂等） | `tools/{order,return,handoff}_tools.py`、`db/repositories/idempotency.py` | `tests/unit/test_return_rules.py`（30）、`test_order_tools.py`、`tests/integration/test_order_return_handoff_db.py` |
| JWT + Argon2 + 算式验证码 + CSRF + 限流 | `core/security.py`、`api/auth.py` | `tests/unit/test_jwt.py`（10）、`test_rate_limit.py`、`tests/integration/test_api_security.py`（22） |
| SSE 七类事件（meta/tool_status/product_card/citation/delta/done/error） | `agents/sse.py`、`api/chat.py` | `tests/unit/test_sse.py` |
| Vue 3 前端（消费者 / 客服 / 管理三端） | `frontend/src`（31 个 `.vue`） | 124 vitest + 16 Playwright |
| 生产部署（只读根文件系统、cap_drop、非 root、资源与日志限制、一次性 migrate） | `compose.prod.yaml`、`web/Dockerfile.prod`、`web/nginx.prod.conf` | `check_deploy_security.py` 34 项；阶段 14 实跑记录（7 容器 healthy、8080 登录成功） |
| 评测与压测工具链 | `scripts/{eval_stage13,verify_stage13,locustfile}.py` | 136 + 58 数据集、8 个 Locust CSV |

### 5.2 已实现但有已知缺陷（**必须带缺陷说**，不能写"完成"）

| 缺陷 | 实测影响 | 证据 | 状态 |
|---|---|---|---|
| 意图路由长尾漏判：政策问题被当闲聊/商品/物流 | 36 条政策类问题只有 **16 条**真正进入 RAG，严格拒答率 0/7 | 报告 2.6、2.9.1 #1 | 未修（需加"知识型兜底"） |
| `PRODUCT_FACT` 与 `PRODUCT_DISCOVERY` 合并到搜索分支，与工具契约不一致 | 9 条用例调用 `search_products` 而非 `get_product_detail`/`check_stock` | 报告 2.9.1 #3 | 未修 |
| 商品对比只认 UUID，抽不到商品名 | 12 条对比用例退化为澄清 | 报告 2.9.1 #2 | 未修 |
| 退货链路拿不到 `order_item_id` | 11 条退货用例未调用 `check_return_eligibility` | 报告 2.9.1 #4 | 未修 |
| **`NO_EVIDENCE` / `CONFLICT` 哨兵 fail-open** | 模型输出 `NO_EVIDENCE [c1]…` 时被当答案返回用户，实测 2 条（`eval-058`/`eval-061`） | `rag/policy_qa.py` L397 精确相等判定；报告 2.9.0 | **未修**（属业务逻辑变更，待所有者授权） |
| 证据门槛是单一相似度信号 | 1 条元信息类问题误拒（`exact-05`） | 报告 2.9.2 | 未修（建议按意图分档） |
| 索引卫生：Milvus 1 条孤儿、21 行 PG chunk 未索引 | 规模口径需分列说明 | 报告 2.9.4 | 未修 |
| `/api/v1/support/*` 未注册 | 前端客服工作台呈错误态 | `docs/06-api.md` §12 勘误 | 未实现 |

### 5.3 未实现 / 计划中（**不得写成已完成**）

- 管理端文档上传、`reindex`、chunk 编辑（只有只读接口）。
- 官方 `ragas` 包（当前是自建 LLM-as-judge，两者不是同一实现）。
- 结构化 faithfulness/relevancy 逐轮落盘（当前需重跑脚本复现）。
- `/metrics` 端点、自动备份任务。
- embedding 独立服务化 / 多副本横向扩展（当前单 worker + 进程内 BGE-M3）。
- 真实数据接入、真实支付/退款、Mock OMS 之外的真实订单系统。
- 跨店铺 admin 运行时用例（知识检索侧已双向验证）。
- 三卷 Milvus 端到端恢复演练（清卷属破坏性操作，未做）。
- docs/09 §7 全量烟测（7.1–7.14）未在容器环境执行。

---

## 6. 关键问题与定位过程（面试最能打的部分）

| # | 现象 | 根因 | 修复 | 证据 |
|---|---|---|---|---|
| 1 | 报告写"136 条评测集"，磁盘只有 100 条，指标复现不出来 | `synthetic/writers.py::write_eval_cases` **无条件重写**评测文件为生成的 100 条，而 `scripts/seed.py` 与 4 个集成测试都会调用它 | 改为"文件存在且非空则不覆盖"；测试断言 `== 100` → `>= 100` | `pytest` 后 `sha256` 仍为 `7606cfce…` / 136 行 |
| 2 | 登录成功后立刻被弹回登录页 | `client.ts` 用模块级 `let accessToken`（非响应式），`isAuthenticated` computed 首次求值后永久缓存 false | 改 `shallowRef`，并加"先求值→登录→clearSession"回归用例 | 118 个 vitest 用例；Playwright 15/15 |
| 3 | 登录失败没有任何提示 | `LoginView` catch 里先赋 `error` 再 `await loadCaptcha()`，后者首行清空 error | 先算 error → 刷新验证码 → 回填 error | 同上 |
| 4 | 刷新页面必回登录页 | 后端登录 cookie `Path=/api/v1/auth`，页面 JS 读不到 CSRF cookie，静默刷新从不发起 | vite 代理与 `web/nginx.conf` 重写 cookie path 兜底（未改后端） | 「实测 reload 后无 `/auth/refresh` 请求」；生产 nginx 生效后刷新保持登录 |
| 5 | 评测 baseline 行为正确率异常掉到 0.8793 | 冲突夹具入库后**污染了其他用例**（评测夹具本身改变了被测系统） | 分阶段隔离：先跑非冲突用例 → 入库夹具跑冲突用例 → 清理 | 修复后回到 0.9828 |
| 6 | 压测吞吐写 22.5→29.4，与 CSV 不符 | 取了旁路估算而不是 CSV 汇总行 | 改读 `Aggregated` 行 `Requests/s`：23.08→29.61（+28.3%） | 两个 CSV 可随时 `grep` 复算 |
| 7 | 延迟 P95 无意义 | 18 个政策检索轮被并进聊天轮列表（n=127 却叫"非检索轮"） | 每条 record 打 `latency_kind`，分桶汇总，只从 records 派生 | 109 / 18 / 9 三桶，`verify_stage13.py` 可复算 |
| 8 | SSE 断线后消息直接消失，无任何提示 | `onSend` 把 `network` 与"用户停止/重复请求"合并处理，`resetTurn()` 丢掉错误态 | 保留 `turn.error` + 重试入口，气泡渲染条件纳入 `error/stopped` | 6 条单测 + 1 条 E2E |

**方法论收获**（可复述）：指标不可复现通常不是脚本算错，而是**输入数据被另一个流程改掉了**；
所以先对账 `sha256 + 行数 + 原始结果里的数据集字段` 三处，再谈指标。

---

## 7. 明确禁止写进简历的表述

| 禁止 | 原因 |
|---|---|
| "自助解决率 82%""缓存命中 42%""成本降低 70%""转化率提升 18%" | 课程场景示例值，本项目未测（`AGENTS.md` §2.3） |
| "混合检索提升召回 xx%" | 58 条数据集上 hybrid 与 dense-only **完全无差异**（报告 2.4.3） |
| "政策问答准确率 88%" | 0.88 只是 5 条上的 LLM 自评忠实度，且含 2 条哨兵泄漏 |
| "RAGAS 指标达到 …" | 官方 `ragas` 包未运行，当前是自建同构/代理实现 |
| "端到端客服系统已完成""全流程可用" | 有 5.2 的已知缺陷与未实现端点 |
| "节省云成本 xx%" | 只有本地 0 USD 口径 |
| "支撑 40 并发，P95 2.4s"当作容量承诺 | 单机单 worker + CPU 推理，已饱和 |
| "参考了 xx 开源项目并实现同样功能" | 参考仓库只借鉴思路，未复制代码 |

### 可以放心写的定性表述

- "把价格/库存/订单等事实收敛到 PostgreSQL 单一来源，模型只做解释，避免 LLM 编造商品事实。"
- "政策回答强制引用文档、章节、版本与生效期；无证据时拒答或转人工。"
- "用独立复算脚本 + 数据集指纹把评测数字做成可审计的，而不是一次性截图。"
- "在 58 条金标上做 dense-only 消融，结论是'测不出差异'，因此没有把它包装成优化成果。"

---

## 8. 复核命令（任何人可重跑）

```bash
# 静态与测试
uv run ruff check .
uv run pytest -q
uv run pytest tests/security -q
cd frontend && npm run typecheck && npx vitest --run

# 评测复算（不连库，只读原始结果 + 数据集）
uv run python scripts/verify_stage13.py

# 数据集指纹
wc -l data/eval/eval_questions.jsonl data/eval/retrieval_cases.jsonl
sha256sum data/eval/eval_questions.jsonl data/eval/retrieval_cases.jsonl

# 压测取数（CSV 汇总行）
grep -i aggregated data/eval/results/locust-stage13-u20_stats.csv
grep -i aggregated data/eval/results/locust-stage13-u40_stats.csv

# 部署安全
uv run python scripts/check_deploy_security.py
```

> **单文件运行的已知限制（未修，仅记录）**：`uv run pytest tests/unit/test_query_rewrite.py` 单独运行会因
> `db/repositories/knowledge.py` 的循环导入在 collect 阶段失败；**全量收集（602 项）不受影响**。
> 需要单跑该文件时，先导入 `shopmate_ecommerce_assistant.db.repositories.knowledge`（或在同一进程内先 collect 整个 `tests/`）。
> 属可维护性问题，非业务缺陷；修复涉及导入顺序调整，本轮未改动代码，以免引入回归。

期望：`600 passed, 2 skipped` / `86 passed` / `124 passed` / `0 不一致项` /
`136` 与 `58` 行 / `7606cfce…` 与 `856f3338…` / `23.0833` 与 `29.6058` / `34 PASS 0 WARN 0 FAIL`。

---

## 9. 与阶段 15 其他产物的关系

| 文件 | 用途 |
|---|---|
| [`interview-prep.md`](interview-prep.md) | 中文简历项目描述（3 个长度版本）+ 15 个面试问答提纲 + 90 秒口述稿 |
| `docs/eval-report.md` | 指标定义、失败案例、整改前后的原始口径（第 2 章） |
| `docs/test-report.md` | 测试与安全矩阵、故障演练（阶段 12） |
| `docs/project-status.md` | 各阶段实施与验收事实（§21 阶段 13、§22 阶段 14） |
| `docs/demo.md` | 可执行的 3 分钟 / 10 分钟演示脚本（阶段 14，v1.0） |
