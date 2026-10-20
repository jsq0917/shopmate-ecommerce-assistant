# ShopMate 测试、安全与故障演练报告（阶段 12）

> 阶段：阶段 12 — 测试、安全与故障演练
> 日期：2026-10-20
> 环境：Windows + Docker Desktop（Linux containers）；PostgreSQL / Redis / Milvus 容器均 healthy
> 状态：**完成**（§16.2 必测项 15/15 有自动化证据；无未处理的高危项）
> 验收：**PASS**（2026-10-20 验收后修复 §11 关闭全部 4 项待修复项）
> 关联：`AGENTS.md` §16、`docs/07-security.md` §15、`docs/06-api.md`、`docs/project-status.md` §20

本报告中的每个数字都来自本轮实际执行的命令输出。没有实测依据的项一律标注为“未验证”或
“缺口”，不写推测结论。

---

## 1. 结论摘要

| 项 | 结果 |
|---|---|
| 后端测试 | **587 passed, 2 skipped**（`uv run pytest -q`，134.76s；收集 589） |
| 后端静态检查 | `ruff check` 通过；`ruff format --check` 213 文件已格式化 |
| 前端类型检查 | `vue-tsc --noEmit` 0 错误 |
| 前端组件测试 | **14 文件 / 124 测试通过**（Vitest） |
| 端到端测试 | **16/16 通过**（Playwright + msedge，51.3s） |
| §16.2 必测项 | **15/15 覆盖**（见第 4 节，逐项列出测试位置） |
| SEC-01–SEC-19（19 项） | **15 项通过 / 3 项部分覆盖 / 1 项无法验证**（见第 5 节；两处数字可用第 5 节表格逐行机械核对） |
| 本轮发现缺陷 | 2 项：1 个测试隔离缺陷（已修）、1 个前端断线静默失败（已修，最小改动） |
| 验收后修复 | 4 项（1 项 P2 + 3 项 P3），见第 11 节；其中 A 项含 1 处业务规则变更 |
| 未处理高危项 | **0** |

本轮**未**新增业务功能、**未**提交 Git、**未**停止/重建任何容器、**未**删除或弱化任何既有测试。

---

## 2. 执行的命令与实测输出

### 2.1 后端

```text
uv run ruff check .                 -> All checks passed!
uv run ruff format --check .        -> 213 files already formatted
uv run pytest -q                    -> 587 passed, 2 skipped, 26 warnings in 134.76s
uv run pytest tests/security -q     -> 86 passed
uv run pytest tests --collect-only -q -> 589 tests collected
```

> 上表为 2026-10-20 验收后修复完成时的实测值；修复前的基线是 576 passed / 2 skipped / 578 collected。

新增用例分布（`--collect-only` 实测）：

| 文件 | 用例数 | 类型 |
|---|---|---|
| `tests/integration/test_api_security.py` | 22（原 19 + 验收后修复补 3 条 admin 路由参数） | HTTP 边界安全 / 故障编排 |
| `tests/unit/test_fault_drill.py` | 11 | 依赖故障注入 / 日志脱敏 |
| `tests/integration/test_retrieval_pipeline.py` | 3（原 2 + 新增 1） | 真实 Milvus + PostgreSQL 跨店铺隔离 |
| `tests/unit/test_return_rules.py` | 30（原 25 + 验收后修复补 5） | 退货规则表（含「已退款/已退货」口径） |
| `tests/integration/test_order_return_handoff_db.py` | 8（原 5 + 验收后修复补 3） | 退货阻断记录的真实数据库行为 |

### 2.2 前端

```text
npm run typecheck                        -> 0 错误
npx vitest --run                         -> 14 files / 124 tests passed（13.95s）
npx playwright test                      -> 16 passed（51.3s）
```

Playwright 使用本机 18001 端口上的本地 API 进程（`VITE_API_PROXY_TARGET=http://localhost:18001`），
未操作任何容器。

---

## 3. 本轮新增/修改的测试文件

| 文件 | 作用 |
|---|---|
| `tests/integration/test_api_security.py` | 新增。越权订单/物流、订单列表作用域、admin RBAC、退货重复提交、Prompt injection、PII 回显、检索/模型故障降级、SSE 断线恢复、日志脱敏 |
| `tests/unit/test_fault_drill.py` | 新增。PostgreSQL / Redis 不可用、模型超时、检索为空、工具失败不循环、`/health` 与 `/ready` 语义、失败日志脱敏 |
| `tests/integration/test_retrieval_pipeline.py` | 修改。`_ingest` / `_cleanup` 支持传入 `shop_id`；新增 `test_another_shops_knowledge_is_never_retrieved` |
| `frontend/src/composables/useChatStream.test.ts` | 新增。流正常/断线/重试恢复/服务端 error/主动停止/409 重复提交 共 6 条 |
| `frontend/e2e/chat.spec.ts` | 修改。新增“SSE 断线：显示可重试错误，重试后恢复” |
| `tests/integration/test_seed_data.py` | 修改。种子断言改为按 `SM-2026-*` 作用域（见 6.1） |

---

## 4. AGENTS.md §16.2 必测项矩阵（15/15）

| # | 必测项 | 测试位置 | 结果 |
|---|---|---|---|
| 1 | 不同用户的订单不能互查 | `tests/security/test_order_permissions.py`、`tests/unit/test_order_tools.py::test_other_users_order_is_same_not_found`、`test_api_security.py::test_another_users_order_is_indistinguishable_from_missing` | 通过 |
| 2 | 订单不存在/已取消/已退款下的退货资格 | `test_return_rules.py::test_cancelled_order_is_not_allowed`、`test_non_active_item_blocks`（参数化含 `returned`）、**验收后修复新增** `test_returned_item_is_never_eligible`、`test_each_open_return_status_blocks_a_duplicate`（3 个状态）、`test_completed_order_with_active_item_stays_eligible_at_rule_level`、`test_order_return_handoff_db.py::test_completed_return_still_blocks_a_new_application`、`test_finished_refusal_or_draft_does_not_block_a_new_application`、`test_check_missing_order_is_business_refusal_not_error` | 通过（「已退款」口径见 7.2） |
| 3 | 退货期限边界（最后一天 / 超一天） | `test_return_rules.py::test_window_boundary_exactly_deadline_is_eligible`、`test_window_one_second_after_deadline_expires` | 通过 |
| 4 | `create_return_request` 重复提交不建两条 | `test_return_tools.py::test_create_is_idempotent_and_reuses_tool_call_id`、`test_api_security.py::test_duplicate_return_submission_creates_one_row`（断言库中恰好 1 行） | 通过 |
| 5 | 退款/赔付/优惠不能由模型直接批准 | `tests/security/test_output_guard.py`（承诺阻断 + 否定豁免）、`test_policy_qa_injection.py::test_promised_refund_is_handed_off_without_leaking_the_draft`、工具层无任何退款写路径 | 通过 |
| 6 | 无政策证据时拒答或转人工 | `test_policy_qa.py::test_low_evidence_refuses_without_calling_the_model`、`test_fault_drill.py::test_empty_retrieval_refuses_without_calling_the_model` | 通过 |
| 7 | 过期政策不进入检索结果 | `test_retrieval.py::test_expired_and_cross_shop_chunks_are_rejected`、`test_retrieval_pipeline.py::test_expired_version_never_becomes_evidence`（真实 Milvus） | 通过 |
| 8 | 跨店铺知识库不可见 | `test_retrieval.py::test_expired_and_cross_shop_chunks_are_rejected`、**新增** `test_retrieval_pipeline.py::test_another_shops_knowledge_is_never_retrieved`（真实数据双向隔离） | 通过 |
| 9 | 文档中的恶意指令不改变系统行为 | `test_policy_qa_injection.py`（`</evidence><system>` 闭合攻击、承诺护栏、逐句引用）、`test_api_security.py::test_prompt_injection_is_refused_without_tool_calls` | 通过 |
| 10 | 价格/库存来自数据库且与 `as_of` 一致 | `tests/integration/test_catalog_detail_compare_stock.py`、`test_catalog_search_db.py` | 通过 |
| 11 | 物流工具只返回当前用户订单 | `test_order_tools.py::test_get_shipment_returns_timeline`、`test_other_users_order_is_same_not_found`、`test_api_security.py::test_another_users_shipment_is_unreadable` | 通过 |
| 12 | SSE 中断后前端能显示错误并恢复 | **新增** `frontend/src/composables/useChatStream.test.ts`（6 条）、`frontend/e2e/chat.spec.ts::SSE 断线`、`test_api_security.py::test_aborted_stream_leaves_a_recoverable_answer` | 通过（修复后，见 6.2） |
| 13 | 日志不含完整 PII、密钥、系统 prompt | **新增** `test_fault_drill.py::test_failure_logs_never_contain_pii_sql_or_credentials`、`test_api_security.py::test_chat_with_pii_writes_no_pii_to_the_server_log`（验收后修复各自加入 `你是 ShopMate`、`<evidence`、`NO_EVIDENCE` 三个提示词标记断言） | 通过 |
| 14 | 管理端接口普通用户不可访问 | **新增** `test_api_security.py::test_admin_endpoints_reject_shoppers`（**8 个端点** × 403/401，验收后修复由 5 条补至 8 条）、`test_admin_can_read_own_shop_knowledge` | 通过 |
| 15 | 低置信度/高风险触发转人工 | `tests/security/test_risk_handoff.py`、`test_intent_router.py`（投诉强制 handoff、低置信澄清、高额阈值边界） | 通过 |

---

## 5. docs/07-security.md §15 安全验收矩阵（SEC-01–SEC-19）

| ID | 结论 | 证据 / 说明 |
|---|---|---|
| SEC-01 普通用户访问客服/管理接口 | 部分 | 管理端 **8 个端点**已验证 403/401（`test_admin_endpoints_reject_shoppers`，GET 5 + POST 2 + 带路径参数 1）；**客服端 `/api/v1/support/*` 路由尚未注册**，请求返回 404，无法验证队列数据隔离（见 7.1） |
| SEC-02 查询他人订单/物流 | 通过 | 越权订单与“不存在订单”返回同一 `ORDER_NOT_FOUND` 与同一文案，响应体不含订单号/地址/运单号；物流端点先校验归属 |
| SEC-03 读取/修改他人会话或工单 | 通过 | `test_api_flow.py::test_cross_tenant_isolation`、`test_handoff_idempotent_replay_and_conflict`（他人工单 404） |
| SEC-04 跨店铺客服/管理员访问 | 部分 | 知识检索双向隔离已用真实数据验证；跨店铺**管理端**因只有一个 demo shop，未构造第二店铺的 admin 会话（见 7.3） |
| SEC-05 无证据政策问题 | 通过 | 固定拒答文案 + 零引用，且不调用回答模型 |
| SEC-06 过期/冲突/跨店铺政策 | 通过 | 过期版本被 `version_not_ready`/过期过滤；版本重叠 → `CONFLICT_TEXT` 转人工；跨店铺双向隔离 |
| SEC-07 恶意文档 Prompt Injection | 通过 | 片段被 `&/</>` 转义，`<system>` 计数为 0，只有一个 `<evidence>` 块 |
| SEC-08 要求输出系统 prompt/密钥 | 通过 | 输入护栏 6 类注入码拦截；API 层验证无工具调用、无 prompt 标记回显 |
| SEC-09 要求他人订单/管理员工具 | 通过 | 越权意图被 `other_user_data`/admin 权限规则拦截；工具白名单拒绝未注册工具 |
| SEC-10 模型文本声称已退款/已赔付 | 通过 | 输出护栏承诺规则阻断并转人工，草稿不外泄 |
| SEC-11 重复退货/工单 | 通过 | 幂等键重放返回同一资源；不同载荷 → 409 `IDEMPOTENCY_CONFLICT` |
| SEC-12 工具连续失败/超时 | 通过 | 单个工具失败即终止本轮（`dispatcher.calls == 1`），返回可重试错误；无重试循环 |
| SEC-13 PII 日志与上下文扫描 | 通过 | 两条日志脱敏用例：失败路径与真实聊天流均不含手机号、地址、SQL、密码、token；验收后修复各加 3 个系统 prompt 标记（`你是 ShopMate`、`<evidence`、`NO_EVIDENCE`），断言日志中不出现提示词与证据块标签 |
| SEC-14 路径穿越/非法类型/超大文件 | 通过 | `test_ingestion.py` 的 `UNSAFE_SOURCE_PATH` / `PARSE_FAILED` / `DOCUMENT_TOO_LARGE` |
| SEC-15 危险 Markdown/HTML/外链 | 通过 | `test_output_guard.py::test_unsafe_html_and_external_link_are_removed` |
| SEC-16 验证码暴力与限流 | 部分 | 限流器单测与 429 契约存在；**验证码暴力破解的端到端计数用例**未单独编写（限流键为 IP+用户，已有实现） |
| SEC-17 缓存版本失效/高风险缓存 | 通过 | `test_faq_cache.py` 的 8 种不可缓存原因、版本指纹失效、命中后仍过护栏 |
| SEC-18 健康检查错误信息 | 通过 | `/ready` 只返回 `ok/error`；异常文本不入响应（`test_fault_drill.py` 两条） |
| SEC-19 回答质量标记权限与审计 | 无法验证 | 该端点（`support:quality_label:write`）在阶段 10 未注册，仅存在权限常量 |

---

## 6. 本轮发现与处理

### 6.1 [测试缺陷·已修] 种子测试被 E2E 遗留数据污染

**现象**：基线 `uv run pytest -q` 有 2 条失败：

```text
FAILED tests/integration/test_seed_data.py::test_seed_counts_metadata_and_idempotency
       assert 101 == 100
FAILED tests/integration/test_seed_data.py::test_seeded_orders_have_unique_numbers_and_consistent_states
       assert 101 == 100 / assert all("合成" in address ...)
```

**根因**：`frontend/e2e/fixture.mjs` 会为 Playwright 幂等写入 1 条 `E2E-*` 合成订单
（`is_synthetic=true`，地址为 `*** 市 *** 区 *** 路 1 号`）。种子测试断言的是**全表** 100 行，
把合法写入的 E2E 数据当成种子输出。

**处理**：断言改为按种子自身契约作用域（`order_no LIKE 'SM-2026-%'`），并保留/加强了强度：

- 种子必须**且只能**产出 100 条 `SM-2026-*` 订单；
- 订单号在**全表**唯一（不因作用域而放宽）；
- 种子的 100 条地址必须含“合成”标记且不含手机号。

未删除测试、未降低断言阈值。这是测试隔离修复，不是产品缺陷。

### 6.2 [产品缺陷·已修] SSE 断线时前端静默失败（P2）

**现象**：新增 E2E 首轮失败——`locator('.sm-bubble-error')` 30s 内不存在。

**根因**（两处，均为显示层）：

1. `frontend/src/views/ChatView.vue::onSend` 把 `outcome === 'network'` 与“用户停止/重复请求”
   合并处理：`resetTurn()` + 重拉历史。错误态被直接丢弃，用户只看到消息消失。
2. `frontend/src/components/chat/ChatThread.vue` 生成流式气泡的条件未考虑 `turn.error`：
   正文为空时即使有错误也不渲染气泡。

**处理（最小改动，仅显示层，不动安全逻辑）**：

- `ChatView.vue`：网络断线不再 `resetTurn()`，保留错误气泡与“重试”入口；重试经 `send()` 自然清空。
- `ChatThread.vue`：空正文但存在 `error`/`stopped` 时仍渲染气泡。

**验证**：`e2e/chat.spec.ts::SSE 断线：显示可重试错误，重试后恢复` 通过（中断一次建流 →
断言错误可见 → 点击重试 → 无错误、历史含用户消息、助手有回答）；`useChatStream.test.ts` 6 条单测覆盖
网络断线、重试恢复、服务端 error、主动停止、409 重复提交。

### 6.3 观察项（未修改，交阶段 13/14 决策）

| 观察 | 影响 | 建议 |
|---|---|---|
| Redis 不可用时限流器异常上抛 → 500 `INTERNAL_ERROR`（fail-closed） | 可用性：Redis 挂 = 登录/聊天全部 503/500 | 行为本身安全（不放行），文案中文可读；若需更高可用性，可在阶段 14 将限流器异常映射为 503 `UPSTREAM_UNAVAILABLE` 并保留 fail-closed |
| 测试日志出现 `InsecureKeyLengthWarning`（16/18/26 字节 HMAC key） | 仅测试夹具使用的短密钥 | 生产配置校验 `JWT_SECRET` ≥32 字节；不属本阶段范围 |
| E2E fixture 订单地址为 `*** 市 *** 区 *** 路 1 号`，无“合成”字样 | 数据卫生；仍是合成且已脱敏 | 可让 fixture 复用种子的“合成”前缀，避免与种子口径混淆 |
| `data/` 下合成文件未纳入 `.gitignore` 也未提交 | 首次 commit 前需决定 | 阶段 14 处理 |

---

## 7. 已知缺口（无法用现有实现验证）

### 7.1 客服工作台路由未注册

`/api/v1/support/*`（工单队列、会话详情、质量标记）在阶段 10 未注册，请求返回 404。
因此 SEC-01 的“客服端”部分与 SEC-19 只能标注**未验证**。前端已按 `docs/06-api.md` 实现，
后端接线后需补：`test_support_tickets_reject_shoppers`、`test_quality_label_requires_support_scope`。

### 7.2 「已退款」状态在数据契约中不存在（等价语义已闭环）

`OrderStatus` 只有 `created/paid/processing/shipped/delivered/completed/cancelled`，**没有订单级 `refunded`**。

「已退款」在本项目的等价语义有两处，且都已有自动化证据：

1. **`order_item.status = returned`**（该明细已退回）：规则层返回
   `ineligible / INVALID_STATE`，用例 `test_return_rules.py::test_non_active_item_blocks`（参数化含
   `returned`）与验收后修复新增的 `test_returned_item_is_never_eligible`。
2. **`return_request.status = completed`**（退货已走完全流程）：仓库层把该状态视为阻断记录，
   `find_active_return` 返回非空 → `has_active_return=True` → `decision_code=DUPLICATE_RETURN`。
   用例 `test_order_return_handoff_db.py::test_completed_return_still_blocks_a_new_application`
   （真实 PostgreSQL：直接断言仓库返回值 + 端到端断言资格检查结果为 `DUPLICATE_RETURN` 且不签发令牌）。

补充口径：**订单状态 `completed` 本身不代表已退款**。`test_completed_order_with_active_item_stays_eligible_at_rule_level`
实测钉住「订单 completed + 明细 active + 窗口内 → `RETURN_ELIGIBLE`」，说明阻断来自退货记录状态，不能来自订单状态。

若产品仍要求订单级 `refunded` 状态，属于数据契约变更，需要单独授权与迁移，本阶段不做。

### 7.3 跨店铺管理端未构造第二店铺会话

知识检索已用真实第二店铺数据双向验证；但 `admin` 跨店铺访问需要两个店铺的 admin 账号与
对应知识库，当前种子只有 1 个 shop。现有证据是「所有 admin 查询带 `shop_id` 且由 token 注入」的
实现检查 + `test_admin_can_read_own_shop_knowledge`，尚缺“admin A 读不到 shop B”的运行时用例。

### 7.4 真实模型测试默认跳过

```text
SKIPPED tests/integration/test_bge_m3_provider.py:36  未设置 SHOPMATE_RUN_MODEL_TESTS=1
SKIPPED tests/integration/test_bge_m3_provider.py:61  未设置 SHOPMATE_RUN_MODEL_TESTS=1
```

原因：需要加载约 2.2 GB BGE-M3 权重，不应成为常规门禁的硬依赖。阶段 7 曾在
`SHOPMATE_RUN_MODEL_TESTS=1` 下实测 2 passed（61.12s），本轮未重复加载模型。
模型真实质量评测属阶段 13（RAGAS / 检索评测）。

### 7.5 admin 部分写端点缺失

`POST /admin/documents`、`POST /admin/documents/{id}/reindex`、`PATCH|DELETE /admin/chunks/{id}`
未注册（阶段 11 已记录）。上传相关的 SEC-14 证据来自 ingestion 管线测试，不是 HTTP 上传端点。

---

## 8. 故障演练矩阵

| 故障 | 注入点 | 期望 | 实测结果 |
|---|---|---|---|
| PostgreSQL 不可用（工具层） | 工具 handler 抛 `OperationalError` | `UPSTREAM_UNAVAILABLE` + 中文可操作文案，不含 SQL/参数 | 通过 |
| PostgreSQL 不可用（API 层） | `session_factory` 抛 `OperationalError` | 统一错误信封 500 `INTERNAL_ERROR`，`retryable=true`，无连接串 | 通过 |
| Redis 不可用 | 限流器抛 `ConnectionError` | 不放行（fail-closed），返回安全可重试信封，不泄露驱动异常 | 通过（500 `INTERNAL_ERROR`） |
| Milvus / 检索不可用 | `PolicyQAService.answer` 抛 `RetrievalError` | 固定降级文案，**无 citation**，`done` 收尾而非 500 | 通过 |
| 模型超时 | `httpx.ReadTimeout` | `AnswerModelError(ANSWER_MODEL_UNAVAILABLE)` → 降级文案，不伪造政策 | 通过 |
| 检索为空 | 返回 `evidence_sufficient=false` | 固定拒答，**不调用模型**，零引用 | 通过 |
| 工具失败 | 工具信封 `ok=false` | 本轮只调用 1 次即终止，受控 `ToolError`（可重试） | 通过 |
| 健康探针 | 依赖全挂 | `/health` 200（仅存活）、`/ready` 503（只给 ok/error） | 通过 |
| SSE 客户端断线 | 读到第 2 个 chunk 后关闭 | 用户消息持久化，历史可拉到本轮回答供恢复 | 通过 |
| 日志脱敏 | 失败路径携带手机号/地址/SQL/密码 | 日志只有稳定文案，无 PII / SQL / 凭据 | 通过 |

说明：本演练通过**代码层故障注入**完成，未停止任何容器。容器级演练（真实 `docker stop`）
需要所有者授权且在隔离环境执行，不在本阶段自动执行。

---

## 9. 复现命令

```powershell
# 后端门禁
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pytest tests/security -q
uv run pytest tests/integration/test_api_security.py tests/unit/test_fault_drill.py -q

# 可选：真实模型测试（需本地 BGE-M3 权重）
$env:SHOPMATE_RUN_MODEL_TESTS = "1"; uv run pytest tests/integration/test_bge_m3_provider.py -q

# 前端门禁
Set-Location frontend
npm run typecheck
npx vitest --run
npm run build
# E2E 需先在本机 18001 启动 API（见 docs/project-status.md），不要使用容器重启
$env:VITE_API_PROXY_TARGET = "http://localhost:18001"; npx playwright test
```

---

## 10. 阶段 12 验收对照

| 验收要求 | 结果 |
|---|---|
| §16 必测项全部覆盖 | 15/15，逐项有测试位置 |
| 安全测试无高危未处理项 | 是（0 项高危；2 个 P2 级缺口记录在 7.1/7.3） |
| 测试失败不被隐藏 | 基线 2 条失败已公开记录并修复（6.1）；跳过项均写明原因 |
| 关键失败有用户可理解的中文提示 | 是（工具/API/检索/模型/SSE/健康探针均有固定中文文案，测试断言中文与非空） |
| 未删除或弱化测试 | 是（唯一断言调整见 6.1，作用域化并加强） |
| 未新增业务功能 | 是（仅两处显示层修复，见 6.2） |

---

## 11. 阶段 12 验收后修复（2026-10-20）

阶段 12 首次验收结论为 **CONDITIONAL PASS**（15 项必测中 14 项证据充分，仅第 2 项口径有缺口）。
本节记录关闭验收清单 4 项（1 个 P2 + 3 个 P3）的改动与实测结果。

### 11.1 A（P2）补齐必测项 2「已退款/已退货状态下的退货资格」

**先钉住现状，再决定是否改业务规则。** 新增的
`test_return_rules.py::test_completed_order_with_active_item_stays_eligible_at_rule_level`
在改动业务代码前先跑了一次，实测结果为 `RETURN_ELIGIBLE`：

```text
uv run pytest tests/unit/test_return_rules.py -q  ->  30 passed
（第 3 条断言 decision_code == "RETURN_ELIGIBLE" 通过）
```

也就是说：**订单 `completed` + 明细 `active` + 窗口内 → 仍可申请退货**。由于 `src/` 中没有任何
代码把 `order_items.status` 写成 `returned`，一次退货被审批为 `completed` 之后，
消费者可以再次提交同样申请 → **重复退货风险成立**。

**因此发生了 1 处业务规则变更（最小改动）**：

| 文件 | 改动 |
|---|---|
| `src/shopmate_ecommerce_assistant/db/repositories/orders.py` | 新增 `_CLOSED_RETURN_STATUSES = (ReturnStatus.COMPLETED,)` 与 `_BLOCKING_RETURN_STATUSES`；`find_active_return` 查询改为按阻断集合过滤（`submitted/under_review/approved/**completed**`；`rejected`/`draft`/`cancelled` 不阻断）；docstring 改为「返回阻断新申请的记录」 |
| `src/shopmate_ecommerce_assistant/domain/orders/ports.py` | `OrderReader.find_active_return` docstring 同步新语义 |
| `src/shopmate_ecommerce_assistant/tools/return_tools.py` | 两处调用点变量 `existing` 重命名为 `blocking_return`（`check_return_eligibility`、`create_return_request`），`_eligibility_data` 形参同步；**逻辑不变** |
| `docs/05-tool-contract.md` | §7.1 规则 8 标注阻断集合含 `completed`；补充说明「已完成退货同样阻断重复申请」、`rejected/draft` 不阻断、DB 部分唯一索引与仓库层的关系 |

新增测试（共 8 条，全部通过）：

| 用例 | 断言 |
|---|---|
| `test_return_rules.py::test_returned_item_is_never_eligible` | `order_item.status=returned` → `INVALID_STATE` |
| `test_return_rules.py::test_each_open_return_status_blocks_a_duplicate`（3 参数：submitted / under_review / approved） | `has_active_return=True` → `DUPLICATE_RETURN` |
| `test_return_rules.py::test_completed_order_with_active_item_stays_eligible_at_rule_level` | 订单 `completed` 本身不阻断 → `RETURN_ELIGIBLE`（口径钉子） |
| `test_order_return_handoff_db.py::test_completed_return_still_blocks_a_new_application` | 真实 PostgreSQL：`find_active_return` 返回非空且 `status=completed`；端到端 `decision_code=DUPLICATE_RETURN`、`can_create_return_request=False`、`eligibility_token=None`、`existing_return.status=completed` |
| `test_order_return_handoff_db.py::test_finished_refusal_or_draft_does_not_block_a_new_application`（2 参数：rejected / draft） | `find_active_return` 返回 `None`，资格检查仍 `RETURN_ELIGIBLE` 且签发令牌（未过度拦截） |

未放宽任何既有断言：`has_active_return` 默认值仍为 `False`，`test_duplicate_active_return_blocks` 保留。

### 11.2 B（P3）修正 §1 摘要数字

以 §5 表格逐行机械核对（19 行）：`通过` 15 行、`部分` 3 行（SEC-01/04/16）、`无法验证` 1 行（SEC-19）。

```text
改前 §1：13 项通过，4 项部分覆盖，2 项因端点未实现无法验证
改后 §1：15 项通过 / 3 项部分覆盖 / 1 项无法验证（并标注“可与第 5 节表格逐行机械核对”）
```

### 11.3 C（P3）admin 路由测试补齐到 8 条

`test_admin_endpoints_reject_shoppers` 参数化由 5 条（全为 GET）扩为 8 条，改为
`(method, template, body)` 三元组以承载 POST；`{document_id}` 用 `uuid4()` 替换：

| 方法 | 路径 |
|---|---|
| GET | `/api/v1/admin/knowledge-bases` |
| **POST** | `/api/v1/admin/knowledge-bases`（body: `{"name": "阶段12 RBAC 知识库"}`） |
| GET | `/api/v1/admin/documents` |
| **GET** | `/api/v1/admin/documents/{document_id}`（`uuid4()`） |
| GET | `/api/v1/admin/chunks` |
| GET | `/api/v1/admin/eval/runs` |
| **POST** | `/api/v1/admin/eval/run`（body: `{"dataset_name": "stage12-rbac", "dataset_version": "v1"}`） |
| GET | `/api/v1/admin/model-profiles` |

断言强度未降：shopper → 403 且 `error.code == "FORBIDDEN"`、响应无 `data`；匿名 → 401 且无 `data`。

### 11.4 D（P3）系统 prompt 不入日志的可执行证据

两条日志脱敏用例的检查集合各加 3 个标记（均为 `rag/policy_qa.py` 中真实存在的字符串：
`SYSTEM_PROMPT` 首句 `你是 ShopMate …`、证据块标签 `<evidence>`、无证据哨兵 `NO_EVIDENCE`）：

- `tests/unit/test_fault_drill.py::test_failure_logs_never_contain_pii_sql_or_credentials`（拒绝集合 7 → 10 项）
- `tests/integration/test_api_security.py::test_chat_with_pii_writes_no_pii_to_the_server_log`（拒绝集合 4 → 7 项）

### 11.5 修复后门禁（2026-10-20 01:30 实测）

```text
uv run ruff check .                          -> All checks passed!
uv run ruff format --check .                 -> 213 files already formatted
uv run pytest -q                             -> 587 passed, 2 skipped, 26 warnings in 134.76s
uv run pytest --collect-only -q              -> 589 tests collected
uv run pytest tests/security -q              -> 86 passed, 8 warnings in 3.10s
uv run pytest tests/unit/test_return_rules.py tests/integration/test_api_security.py tests/unit/test_fault_drill.py -q
                                             -> 63 passed, 5 warnings in 9.70s
docker compose config                        -> 通过（无输出即成功）
cd frontend && npm run typecheck             -> 0 错误
npx vitest --run                             -> 14 files / 124 tests passed
VITE_API_PROXY_TARGET=http://localhost:18001 npx playwright test -> 16 passed (51.2s)
```

数量守卫（无 commit，用数量守恒）：后端 **576 → 587**（+11 = 5 `test_return_rules` + 3
`test_order_return_handoff_db` + 3 admin 路由参数化）；vitest **124 → 124**；Playwright **16 → 16**。
无删除、无 `.only`/`.skip` 新增。
