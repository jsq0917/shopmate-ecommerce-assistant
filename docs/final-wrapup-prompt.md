# ShopMate 最终收尾提示词（阶段 16 · Final Wrap-up）

> 用途：把下面「提示词正文」整段复制给 WorkBuddy / Codex，在新聊天里执行项目最后一次收尾。
> 依据：2026-10-20 11:38 只读复核结果（阶段 0–15 全部 PASS，仍有 4 类遗留）。
> 结构：W1 Git 基线（必做）→ W2 补 4 组后端端点（可选但建议）→ W3 修 fail-open（必做）→ W4 收尾验证与文档（必做）。
> 如果只想做最小收尾，删掉 W2 整段（含 W2.6）即可，其余不受影响。

---

## 提示词正文（从下一行开始整段复制）

你是 ShopMate 项目的收尾执行者。工作目录：`E:\project\shopmate-ecommerce-assistant`。

### 第一步：开工检查（只读，不改任何文件）

1. 确认工作目录正确。
2. `git status --short`，记录当前未跟踪/已修改文件。
3. **完整读取 `AGENTS.md`**（全文，不要只读前几百行，不要依赖历史记忆）。
4. 再按需读取以下文件，不要递归扫描全盘：
   - `docs/06-api.md` §12（客服工作台 API）、§13（管理端 API）、§15（API 验收）
   - `docs/project-status.md` §22.7、§23.6
   - `docs/09-release-checklist.md` §7（功能烟测 7.1–7.14）、§10（实测记录）
   - `docs/eval-report.md` §2.9.0（fail-open 记录）
   - `src/shopmate_ecommerce_assistant/main.py`、`api/admin.py`、`core/security.py`
   - `db/models/support.py`、`db/models/enums.py`、`db/repositories/handoff_read.py`、`db/repositories/knowledge_admin.py`、`db/repositories/audit.py`
   - `rag/ingest/pipeline.py`、`rag/policy_qa.py`
   - `frontend/src/api/endpoints.ts`（L180–245）、`frontend/src/api/types.ts`（L540/L597/L605）
5. 用 **≤15 行**输出：将读什么、将改什么、如何验证、风险与需要我确认的点。

### 背景（已核实，不要重新论证、不要推翻）

- 阶段 0–15 全部完成并通过验收；阶段 15 于 2026-10-20 11:45 判定 **PASS**，口径是"可进入最终演示/交付"。
- 门禁基线（2026-10-20 11:41 实测，作为你改动前的对照）：
  - `uv run ruff check .` → All checks passed
  - `uv run pytest -q` → **600 passed, 2 skipped**（135.76s）
  - `uv run python scripts/verify_stage13.py` → 全部一致，退出码 0
  - 数据集指纹：`data/eval/eval_questions.jsonl` 136 条 / `7606cfceb6ad101c…`；`retrieval_cases.jsonl` 58 条 / `856f3338d00b8c44…`
- 本次**不是重做阶段**，只处理下列 4 个已确认遗留项。不新增产品功能，不做重构。

### 授权边界

本提示词即视为对 **W1–W4** 的执行授权，不需要再问我"是否确认执行阶段"。

但以下操作**必须先停下单独问我**：

- `git push`、打 tag、改远端配置
- 删除/重建容器、删除卷、`docker compose down`
- 破坏性数据库操作（drop、truncate、清库、清 Milvus 卷）
- 修改 `data/eval/` 下任何**已归档**的原始结果或数据集
- 修改评测口径、gate 阈值、已对外发布过的数字
- 在 W2 中发现"文档契约与现有表结构冲突且必须改已有列"的情况

### 铁律（违反即停下并回滚该步）

1. 只改本提示词范围内的文件；不顺手做"阶段 17"，不做大重构。
2. 不得修改 `data/eval/results/stage13-20261020T013230Z.json`、`eval_questions.jsonl`、`retrieval_cases.jsonl`。
   所有评测数字只能来自 `scripts/verify_stage13.py` 的复算输出。
3. 不得为了"让测试过"而放宽断言、加 skip、改测试预期数量。测试数只增不减。
4. 每条"已完成"必须有命令输出作证据；没跑就写"未验证 + 原因"，不许写成"通过"。
5. 除 W1 允许**本地** `git commit` 外，不做任何 Git 写操作（不 push、不打 tag）。
6. 不启停容器、不改 `compose.yaml` / `compose.prod.yaml`（W4 的烟测若需要启动环境，先问我）。

---

## W1 · Git 基线（最重要，先做）

**现状（写这份提示词时，2026-10-20）**：仓库 0 commit，`git log` 报 `your current branch 'main' does not have any commits yet`，全部文件为 `??` 未跟踪。

> **已完成**：该任务已执行完毕。截至 2026-10-23 16:0x 共有 10 个提交（全部已推送 GitHub），见 `docs/project-status.md` §0.2。此段保留为任务背景，不代表当前状态。

**执行**：

1. 只读核对 `.gitignore` 是否已覆盖：`.venv/`、`node_modules/`、`frontend/dist/`、`models/`（BGE-M3 权重约 2.2GB）、`.env` / `.env.*`（同时保留 `!.env.example`、`!.env.prod.example`）、`__pycache__/`、`.pytest_cache/`。
   核对 `data/`（约 4.9MB）与 `data/eval/results/`（约 4.3MB 评测证据）**应当入库**，不得被忽略。
2. 敏感信息扫描（命中即停下报告，不要自行删除或替换）：
   - `git status --short` 清单中不得出现 `.env`、`*.key`、`*.pem`、`*.p12`、`id_rsa`
   - 对将入库文件扫 `BEGIN PRIVATE KEY`、`sk-`、`AKIA`、`shopmate-dev-`、`postgresql://.*:.*@` 等模式，确认命中的都是 `.env.example` 里的占位值
3. **分两个 commit**，不要合成一个：
   - commit 1：`chore: 建立仓库基线（源码/测试/脚本/前端/编排/配置模板）`
   - commit 2：`docs: 补齐阶段 0–15 文档与评测证据`
4. 输出 `git log --oneline` 与 `git status --short`（commit 后应为空），并报告两个 SHA。

**验收**：`git log --oneline` 至少 2 条；`git status --short` 为空；`.env` 与 `models/` 未被跟踪。

---

## W2 · 补齐 4 组后端端点（可选但强烈建议；按子步骤做，每步过测试）

**为什么做**：前端已经在调用这些路径，后端没实现 → 客服工作台整页错误态、管理端上传/编辑按钮失效。这是唯一"功能未闭环"项，`docs/06-api.md` §12/§13 的注记也一直写着"未实现"。

**已核实的现状（直接用，不要再重复排查）**：

| 项 | 事实 |
|---|---|
| 路由注册 | `main.py` L254–263 只注册 `health / system / auth / conversations / chat / catalog / orders / returns / handoff / admin`，**没有 support** |
| 缺失路由文件 | `api/` 下**没有** `support.py` |
| `api/admin.py` 已有 | `GET knowledge-bases`、`POST knowledge-bases`、`GET documents`、`GET documents/{id}`、`GET chunks`、`GET eval/runs`、`POST eval/run`、`GET model-profiles` |
| `api/admin.py` 缺失 | `POST /admin/documents`（上传）、`PATCH /admin/chunks/{id}`、`DELETE /admin/chunks/{id}`、`POST /admin/documents/{id}/reindex` |
| `db/repositories/knowledge_admin.py` | 只有 `list_knowledge_bases / create_knowledge_base / get_knowledge_base / list_documents / get_document / list_chunks / list_eval_runs / create_eval_run`，**无写片段、无上传、无 reindex** |
| `db/repositories/handoff_read.py` | 只有消费侧 `list_for_user / get_for_user`，**无客服队列/详情/状态流转/质量标记** |
| `HandoffTicket` 字段 | 有 `status`（枚举 `HandoffStatus` = open/assigned/resolved/closed）、`assigned_to`、`resolved_at`、`priority`、`risk_rule_codes_jsonb`、`summary_redacted`；**没有** `resolution_summary`、`close_reason` |
| 质量标记 | **没有对应表/模型**，需新增 |
| 权限码 | `core/security.py` L42–45 已有 `support:ticket:read / support:ticket:write / support:conversation:read / support:quality_label:write`，可直接用 |
| 入库能力 | `rag/ingest/pipeline.py::ingest_source` 可复用 |
| 迁移链 | head = `20261019_0004`（`20261018_0001` → `0002` → `0003` → `0004`） |
| 前端 | `endpoints.ts` L185–238、`types.ts` L540/L597/L605 **已按契约写好，不要改**（除非字段名确实对不上，那先报告） |

**子步骤（每步做完先跑测试再继续）**：

- **W2.1 契约对齐**：逐个端点把 `docs/06-api.md` §12/§13 的请求/响应字段与现有表/模型比对，输出一张"文档要什么 / 库里有什么 / 缺什么"的差异表（≤20 行）。
- **W2.2 迁移**：按差异表新增 `alembic/versions/20261020_0005_final_wrapup_support_admin.py`，`down_revision = "20261019_0004"`。**只加列/加表**，不改已有列类型、不删数据、不回填历史语义。执行 `alembic upgrade head` 验证（这是允许的写操作）；**不许** drop / 重建库。
- **W2.3 仓储层**：
  - 客服侧：工单队列（按 `risk_level` + 等待时长排序，字段见 §12 列表项）、工单详情（会话/退货安全摘要 + 引用 + 工具摘要 + 风险）、`assign/resolve/close` 状态机（非法转换抛 `409 INVALID_STATE`）、质量标记写入。
  - 管理侧：上传（创建 document + version + ingestion job，复用 `ingest_source`）、chunk 文本编辑（重算 `content_hash`、失效缓存、返回 `reindex_required=true`）、chunk 软删除、reindex（创建新 ingestion job）。
- **W2.4 路由层**：新建 `api/support.py` + 扩充 `api/admin.py`。所有查询必须带 `shop_id` 作用域，权限用现有 permission code，写操作记审计（复用 `db/repositories/audit.py`），响应走现有 `envelope.py`。响应不得含完整 PII / 系统 prompt / 内部堆栈。
- **W2.5 测试**（数量只增不减）：
  - unit：非法状态转换 409、跨店权限 403、`support:conversation:read` 默认不给 admin、PII 脱敏、上传超 20MiB 拒绝、MIME/魔数不匹配拒绝、chunk 改后 `reindex_required=true`、质量标记归属校验。
  - integration：客服队列查询、工单详情、质量标记写入与越权拒绝。
- **W2.6 文档同步**：把 `docs/06-api.md` §12/§13 的"尚未注册/未实现"注记改为"已实现（阶段 16）+ 实测命令"；`README.md` §9、`docs/08-deployment.md` §12 的已知缺口表相应改写；`docs/09-release-checklist.md` §7.14 从"预期错误态"改为正常验收项。

**W2 验收**：`uv run pytest -q` 全绿且总数 > 600；`GET /api/v1/support/tickets` 用 `support01` 返回 200 且字段与 §12 一致；消费者 token 访问返回 403；上传一个真实 md 文件返回 202 并能在 `GET /admin/documents` 看到 `parse_status`；`PATCH /admin/chunks/{id}` 返回 `reindex_required=true`。

> 如果评估后认为 W2 工作量超出本次能安全完成的范围，**不要半途停在新路由只写一半的状态**——要么按子步骤做完并全绿，要么在执行前就明确告诉我"W2 需要拆分到下一次"，先做 W1/W3/W4。

---

## W3 · 修 `NO_EVIDENCE` fail-open（安全缺陷，改动小）

**现状**：`src/shopmate_ecommerce_assistant/rag/policy_qa.py:276`

```python
if text.strip() in {"NO_EVIDENCE", "CONFLICT"}:
    return issues
```

精确相等才放行。当模型输出 `NO_EVIDENCE [c1]` 时：`strip()` 不等于哨兵 → 走标签校验 → `c1` 是唯一合法标签 → 该句被判为"已标注" → **哨兵串被当成正常答案返回用户**。`eval-058`、`eval-061` 是实证用例。

**要求**：

1. 哨兵判定改为"剥离引用标签 `[cN]`、首尾空白与句末标点后再匹配 `NO_EVIDENCE` / `CONFLICT`"，命中即走拒答 / 转人工分支，绝不进入答案正文或引用展示。
2. 补 unit 测试：`NO_EVIDENCE`、`NO_EVIDENCE [c1]`、`conflict。`、`NO_EVIDENCE[c1].`、正常含标签答案（不得误伤）五种输入。
3. 跑 `uv run pytest -q` 确认无新增失败、无新增 skip。
4. **不得**重跑或改写已归档的 stage13 原始结果；在 `docs/eval-report.md` §2.9.0 追加"已修（阶段 16）"注记，并明确写明：报告内历史数字对应**修复前**行为，修复后的行为由新增 unit 测试覆盖，未重跑全量评测。

**W3 验收**：新增测试全过；`verify_stage13.py` 仍退出码 0（历史结果未被改动）。

---

## W4 · 收尾验证与文档（必做）

1. **全量门禁**，逐条贴输出：
   - `uv run ruff check .`
   - `uv run pytest -q`（记录总数，与 600 对比，说明增量来自哪些测试文件）
   - `uv run python scripts/verify_stage13.py`
   - `uv run python scripts/check_deploy_security.py`
   - `cd frontend && npm run typecheck`（若 W2 未动前端应仍为 0 错误）
2. **烟测**：按 `docs/09-release-checklist.md` §7 逐条跑 7.1–7.14，**逐条**写"通过 / 失败 / 未验证 + 原因"。环境未就绪就写未验证，**不许**用旧记录冒充本轮结果。若需要启动容器，先问我。
3. **文档更新**：
   - `docs/project-status.md` 新增 `## 24. 阶段 16（最终收尾）`：范围、逐条改动、实测输出、仍剩什么。
   - `docs/09-release-checklist.md` §10 追加一行实测记录（日期 / 环境 / 结果 / 备注）。
   - `README.md` 项目状态段同步；`docs/README.md` 索引若新增文档则补一行。
   - 若 W2/W3 改变了任何对外表述，同步 `docs/resume-evidence.md`、`docs/interview-prep.md` 中相关口径——**只允许把"未实现/已知缺陷"改成"已实现/已修复 + 证据"，不许调高任何数字**。
4. **最终报告**（中文，≤40 行）：
   - 改动文件清单（按 W1–W4 分组）
   - 每条门禁命令的关键输出行
   - 本次关闭了哪些遗留、还剩哪些（必须包含"未在全新主机按 README 从零复核""Milvus 三卷未端到端恢复""官方 ragas 未跑"这三条，除非本次真的做了）
   - 两个 commit 的 SHA

### 停止条件（遇到就停下问我，不要自行决定）

- 发现文档契约与现有表结构冲突到必须改已有列或改语义
- 发现仓库里有真实密钥 / 真实 PII
- 任何一步测试出现**改动前不存在**的失败，且 30 分钟内定位不到根因
- 需要启停容器、删卷、drop 表、`git push`
- W2 的某端点实现需要修改 `docs/06-api.md` 已声明的响应字段（即改契约）

---

## 提示词正文结束

---

## 使用说明（给你自己看，不用复制）

1. **开新聊天**再发，避免旧上下文干扰判断。
2. 第一轮它会先给 ≤15 行计划。确认无误后再让它执行；如果它想跳过 W1 直接写代码，打回去。
3. **W2 是唯一有真实工作量的一块**（新路由 + 迁移 + 仓储 + 测试），预计会分多轮。其余三块都很小：W1 五分钟，W3 半小时，W4 一小时。
4. 如果时间紧、只想交付，**删掉 W2 整段 + W2.6**，保留 W1/W3/W4，项目仍然自洽——只是客服工作台和管理端上传按钮继续不可用，且这几条必须继续写在"已知缺口"里。
5. 收尾完成后，`docs/project-status.md` §24 就是最终交付说明；`docs/09-release-checklist.md` §10 是发布证据。
