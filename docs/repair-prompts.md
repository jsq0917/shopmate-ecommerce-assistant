# ShopMate 修复提示词集

> 用法：**一次只喂一条**，每条都要求 agent 先出方案再改代码；做完一项、跑完测试、核对验收标准，再喂下一条。
> 每条提示词前可以加一句："先完整读取 `AGENTS.md` 与 `docs/project-status.md`，再执行本条任务。"
> 顺序不要跳：0 是止血，1-4 是硬伤（影响简历数字），5-7 是课程任务书符合度，8 是文档收尾。

| 序号 | 任务 | 预计产出 | 是否阻塞其他任务 |
|---|---|---|---|
| 0 | 止血：API 崩溃 + 工作区提交 | 容器 healthy、代码进 git | **是**，必须最先做 |
| 1 | 意图路由知识型兜底 | 严格拒答率 0/7 改善 | 是（4 依赖它） |
| 2 | 三个工具契约缺陷 | 任务成功率 0.63 → 0.85+ | 是（4 依赖它） |
| 3 | 扩充语料 + 重建索引 + 重跑评测 | 语料 400-800 chunk，指标有意义 | 是（4 依赖它） |
| 4 | LLM 统一 DeepSeek 档 + 阈值口径 | DeepSeek 上的生成指标、去掉本地小模型基线 | 否（但建议在 1-3 之后） |
| 5 | 知识库多选（任务书要求） | 对话页可勾选 1..N 个 KB | 否 |
| 6 | 推理参数面板（任务书要求） | 温度/topP/max_tokens/历史轮数 | 否 |
| 7 | 图片解析（可选） | 图片文档可入库 | 否 |
| 8 | 文档同步 | 三份过期文档对齐实际 | 建议最后做 |

---

## 提示词 0 — 止血：修复 API 崩溃并提交工作区

```text
【任务：止血 — 修复 API 崩溃并提交当前工作区】

背景：shopmate-api-1 当前 Restarting (255)。日志循环报：
FAILED: Can't locate revision identified by '20261022_0007'
已确认根因：数据库 alembic_version = 20261022_0007（宿主机曾执行 uv run alembic upgrade head，
应用了未提交的两个迁移 20261022_0006_checkout_refunds / 20261022_0007_message_cards），
但 shopmate-api:0.1.0 镜像构建于这两个迁移之前，容器内 alembic/versions 缺少对应文件，
启动时 upgrade head 找不到当前版本而退出。

要求（按顺序，每步先说明再执行）：
1. 只读复核：docker compose ps、docker compose logs --tail=30 api、
   docker exec shopmate-postgres-1 psql -U shopmate -d shopmate -tAc "SELECT version_num FROM alembic_version;"、
   确认工作区两个迁移文件存在且 revision 链衔接（down_revision 指向 0005 / 0006）。
2. 给出重建方案（预期：docker compose build api && docker compose up -d api），
   明确说明不改数据卷、不 down、不 prune，等我确认后执行。
3. 重建后验证：api healthy；/health 与 /ready 均 200；登录 shopper01 后发一条消息能看到 SSE 流。
4. 提交工作区：当前 57 个修改文件 + 约 15 个未跟踪文件（含 0006/0007 迁移、CheckoutView/RefundsView/
   useCart/ProductThumb/persona.py、demo_orders.py、docs/screenshots/）。
   先 git status --short 分类列出，再按「迁移与后端 / 前端 / 文档与脚本」拆成 2-3 个提交，
   提交信息用中文并遵循现有风格（feat:/fix:/docs:/chore:）。
   注意：.workbuddy/ 是本地记忆目录，不得提交。
5. 输出：修复前后容器状态、/ready 输出、git log --oneline 新增提交、仍未跟踪的文件清单。

约束：
- 不执行 docker compose down / prune / volume rm。
- 不改 .env 中的任何口令。
- 提交前跑 uv run ruff check . 与 uv run pytest -q，结果附在报告里。
```

---

## 提示词 1 — 意图路由知识型兜底（严格拒答率 0/7 的根因）

```text
【任务：修复意图路由长尾漏判（严格拒答率 0/7 的根因）】

现状证据（docs/eval-report.md 2.6 / 2.9.1、docs/resume-evidence.md 5.2）：
- 136 条业务用例上意图准确率 0.7059（96/136）、任务成功率 0.6324（86/136）
- 36 条政策类问题只有 16 条真正进入 RAG；7 条 no_answer 用例严格拒答率 0.00（0/7）
- 根因：agents/router.py 是关键词加权规则，长尾政策表述（如"签收后发现屏幕有裂纹还能退吗"）
  被误判为闲聊/商品/物流，未进入 PolicyQAService，因此永远走不到拒答或引用路径

目标（只改路由，不动检索与生成）：
1. 新增"知识型兜底"分支：当规则未命中任何业务意图，但满足以下任一条件时，进入政策 RAG 拒答路径
   （即调用 PolicyQAService 让它按证据门槛决定答/拒，而不是直接回闲聊）：
   a) 包含政策/售后/物流/保修/退款/发票/价保等领域词表（词表外置到常量或配置，可单测）
   b) 形如疑问句（含 吗/呢/怎么/如何/能不能/可不可以/是否/多久/多少钱 等）且长度 ≥ 8 字
   c) 带问号且不含明确的商品搜索/订单查询动作词
2. 兜底分支必须可关闭（环境变量或配置项），默认开启，便于消融对比。
3. 补单测：长尾政策问句 10 条必须路由到政策路径；明确的商品搜索/闲聊/订单查询 10 条不得被兜底抢走。
4. 不修改现有 56 条路由单测的既有断言（如需调整必须逐条说明理由）。

验收：
- uv run pytest tests/unit/test_intent_router.py -q 全绿（含新增用例）
- 重跑业务评测：uv run python scripts/eval_stage13.py --parts business --output /tmp/eval-intent.json
  对比修复前后：意图准确率、严格拒答率（0/7 → ?）、任务成功率；数字写进 docs/eval-report.md 新小节
- 如果严格拒答率仍不达标，先给失败用例清单和原因分类，不要自行放宽证据门槛

约束：先出方案（改哪些文件、词表怎么放、兜底优先级如何插入），我确认后再改代码。
```

---

## 提示词 2 — 三个工具契约缺陷（合计 32 条失败用例）

```text
【任务：修复三个工具契约缺陷（合计 32 条失败业务用例）】

现状证据（docs/eval-report.md 2.9.1、docs/resume-evidence.md 5.2）：
1. PRODUCT_FACT 与 PRODUCT_DISCOVERY 都路由到 search_products —— 9 条用例应调
   get_product_detail / check_stock 却调了搜索，与 docs/05-tool-contract.md 不一致
2. 商品对比只认 UUID，抽不到商品名 —— 12 条对比用例退化为澄清
3. 退货链路拿不到 order_item_id —— 11 条退货用例未调用 check_return_eligibility

要求（逐项，每项先给方案）：
1. 按契约分流：PRODUCT_FACT（问参数/价格/库存/规格）→ detail 或 check_stock；
   PRODUCT_DISCOVERY（找商品/推荐/比价）→ search_products。更新路由与工具选择逻辑，补 9 条对应单测。
2. 商品对比：在 query_understanding 里先解析商品名称/型号 → search_products 解析为 SKU → 再调 compare。
   解析不到时才走澄清文案（保留现有澄清分支）。补 12 条单测。
3. 退货链路：从最近订单工具结果或 checkout 上下文取 order_item_id；会话里没有订单上下文时，
   先查最近可退订单再判定资格。补 11 条单测。
4. 每项修复都要有"修复前/后"的用例断言对比，禁止只改代码不补测试。

验收：
- uv run pytest -q 全绿（基线 600 passed, 2 skipped，新增用例后数量应增加）
- 重跑 business 评测，输出意图准确率 / 工具选择准确率 / 任务成功率三项修复前后对照
- 失败用例从 50 条降到 ≤ 20 条，并列出剩余失败分类

约束：一次只做一项，做完一项跑完测试再进下一项；不要顺手改无关模块。
```

---

## 提示词 3 — 扩充语料 + 重建索引 + 重跑评测

```text
【任务：扩充知识语料，让检索指标重新有意义】

现状：Milvus 仅 28 条向量（27 条有效 + 1 条孤儿），21 个 ready 文档版本；58 条金标上
Recall@1/3/5/10 全部 1.00、MRR 1.00，已饱和；hybrid 与 dense-only 完全无差异——
docs/resume-evidence.md 已注明"不可外推到万级知识库"。这导致简历上的混合检索/重排无法自证价值。

目标：
1. 扩充 data/knowledge/policy/ 语料：目标 60-100 个文档版本、400-800 个 chunk。
   来源：现有政策文档的变体（不同地区/年份/品类），新增 3 个品类（如服饰/家居/数码）的
   售后政策、保修条款、发票与价保规则；全部标记 synthetic。
   版本关系要真实：同一政策保留多个生效期版本，便于验证"版本+生效期过滤"。
2. 同步扩充 data/eval/retrieval_cases.jsonl 到 120-150 条，覆盖 normal / no_answer / expired /
   conflict / cross_shop 五类；补足"同一问题不同版本答案"的用例。
3. 重建索引（scripts/rebuild_knowledge_index.py），修掉孤儿 chunk 与 PG/Milvus 不一致：
   重建后必须输出对账（PG children / Milvus count / 交集 / 孤儿 = 0）。
4. 重跑 retrieval（hybrid + dense_only 消融）、business、generation 三部分，
   数字写入 docs/eval-report.md 新章节，并更新 verify_stage13.py 的复算口径。
5. 在扩大的语料上重新标定证据门槛（dev/test 分开，禁止用 test 调参），记录标定过程。

验收：
- 索引对账：PG children == Milvus count，孤儿 0
- 新语料下 Recall@1 允许 < 1.00（这是好事）；hybrid 与 dense-only 若出现差异如实记录，无差异也照样记录
- uv run python scripts/verify_stage13.py 输出 0 不一致项
- 更新 docs/resume-evidence.md 第 4.1 节（语料规模、指标、口径）

约束：语料必须自造，不得抓取真实企业文档；重建前说明数据卷影响；不动 .env 阈值。
```

---

## 提示词 4 — LLM 统一 DeepSeek 档 + 阈值口径

```text
【任务：LLM 统一走 DeepSeek，移除本地小模型评测基线】

现状：
- .env：LLM_BASE_URL=https://api.deepseek.com，LLM_MODEL=deepseek-v4-flash，temperature 0.1
- 阶段 13 评测：本地 Ollama qwen2.5:7b（已判定规模太小，不再作为评测基线）
- 课程任务描述：要求通义千问 / qwen-max（本决策已知偏差，在 README 注明即可）
- 阈值：.env 与 compose 默认 POLICY_MIN_EVIDENCE_SIMILARITY=0.42，但评测用的是 0.62

决策（已确认，不要推翻）：
- 生产、开发、评测统一使用 DeepSeek（OpenAI 兼容端点），不再依赖本地 Ollama 小模型。
- qwen 档仅以一行注释保留在 .env.example，供临时对齐课程任务书时切换，不作为默认。

要求：
1. 统一 LLM 配置：默认 LLM_MODEL=deepseek-v4-flash（沿用 .env 现有值），
   删除 .env / compose / .env.example 中把本地 Ollama 作为基线的表述；
   代码里若存在 local 分支，保留但标注"仅离线烟测，不用于评测"。
2. .env.example：默认 DeepSeek 档（base_url=https://api.deepseek.com）；
   qwen-max（dashscope 兼容端点）以注释形式保留一行；不写任何真实 key；
   LLM_TEMPERATURE / max_tokens / timeout 保持可配。
3. 阈值统一为 0.62（沿用评测标定）：compose.yaml 默认值、.env、.env.example、docs 四处一致；
   若确需 0.42 作宽松演示档，README 必须写清差异与适用场景。
4. 在 DeepSeek 上重跑 generation 部分：可答用例应答率（原 5/29，本地 7B 基线）、
   严格拒答率（原 0/7）、faithfulness、answer relevancy、引用合规率、平均延迟、token 消耗。
   全部更新到 docs/eval-report.md 与 docs/resume-evidence.md，标注"模型：deepseek-v4-flash"。
5. 更新 README §3/§7 与 docs/08-deployment.md 的模型说明，删除"默认本地 7B"表述；
   加一行说明：课程任务书要求 qwen-max，如需对齐可切 LLM_PROFILE=qwen（兼容端点已支持）。

验收：
- 全仓库 grep 不再把"Ollama / qwen2.5:7b"作为当前基线出现（历史记录可保留并标注"历史"）
- .env.example 可直接 cp 后填 key 启动，无缺失变量
- generation 在 DeepSeek 上有完整数字，uv run python scripts/verify_stage13.py 复算 0 不一致
- 相比本地 7B 基线，至少一项指标可量化改善（可答应答率上升或严格拒答率改善）

约束：不改业务逻辑；跑不通就如实报告，禁止伪造数字；
禁止把 qwen 的旧数字当成 DeepSeek 数字使用。
```

---

## 提示词 5 — 对话页知识库多选（课程任务书硬性要求）

```text
【任务：对话页支持多知识库选择（课程任务描述硬性要求）】

现状：ChatStreamRequest 只有 conversation_id / message / client_message_id；
检索按用户+店铺+地区+语言+版本过滤，没有"用户勾选知识库"的概念。
任务描述原文："对话页面支持用户选择知识库，知识库可以选择一个或者多个"。

要求：
1. 后端：会话级保存 knowledge_base_ids（一个或多个，空 = 全部可见知识库）；
   检索时并入 Milvus 过滤条件 + PostgreSQL 复核；校验每个 kb 属于当前 shop 且用户可见。
   新增 PATCH /api/v1/conversations/{id}/knowledge-bases 或在创建会话时接收。
2. 前端：对话页顶部知识库多选（下拉/标签），默认全选；切换后新消息生效，历史消息不受影响；
   空选时给明确提示。
3. 测试：单测覆盖"选 2 个 kb 只召回这 2 个""选其他店铺 kb 被拒""空选回落全部"；补前端组件测试。

验收：uv run pytest -q 全绿、npm run typecheck + vitest 全绿、Playwright 通过
（多选 kb → 提问 → 引用只来自所选 kb）
约束：先给 API 契约变更方案（含 OpenAPI 影响）再动手；不破坏现有单会话行为。
```

---

## 提示词 6 — 推理参数面板（课程任务书硬性要求）

```text
【任务：对话页推理参数面板（课程任务描述硬性要求）】

现状：LLM_TEMPERATURE 只能改 .env；ChatStreamRequest 无可调参数。
任务描述要求：温度、topP、最长输出 token 数、历史对话轮数，均可从对话页配置。

要求：
1. 后端：会话或请求级参数（temperature 0-1、top_p 0-1、max_tokens、history_turns 0-10），
   带范围校验与安全上限（防 max_tokens 过大拖垮服务）；写入 LLM 调用；
   历史轮数影响上下文拼装（先查清现状是全部历史还是固定值，再改为可配）。
2. 前端：对话页参数面板（滑杆/数字输入 + 恢复默认），参数随会话保存、刷新不丢，展示当前生效值。
3. 测试：参数越界被拒、history_turns=0 不带历史、max_tokens 生效（mock LLM 断言 payload）、
   SSE 流不受影响。

验收：uv run pytest -q 全绿、前端 typecheck+vitest 全绿、手动演示 temperature 0→1 可看出差异
约束：先出方案（参数存会话表还是请求体，二选一并说明理由）再动手。
```

---

## 提示词 7 — 图片文档解析（可选扩展）

```text
【任务（可选扩展）：支持图片文档解析】

现状：rag/ingest/loaders.py 支持 pdf/docx/pptx/md/txt，无图片。
任务描述要求离线文档支持"PDF、PPT、Markdown、图片等类型"。

要求：
1. 图片（png/jpg/jpeg）走两条路任选其一并说明理由：
   a) OCR（PaddleOCR/RapidOCR）→ 文本块入库；
   b) 多模态模型生成图片描述 → 描述入库（需配置视觉模型）。
2. 入库保留 image_url / 文件名 / 尺寸元数据，引用可回溯到原图。
3. 测试：1 张含文字的政策截图能被检索命中；非法格式被拒。

验收：pytest 全绿；检索金标里加 3 条图片类用例
约束：这是可选扩展，先评估工作量与模型依赖，给出 1 页方案让我决定做不做；不要引入重型依赖。
```

---

## 提示词 8 — 三份文档同步

```text
【任务：同步三份脱节文档】

现状：
- docs/project-status.md 头部仍写"当前阶段：阶段 13…阶段 14 未开始"，实际已完成阶段 16 且有 checkout/refunds 新工作
- docs/resume-evidence.md §0 仍写"本仓库当前 0 个 commit"，实际已有 4 个 commit 并推送 GitHub
- README §9 与 docs/06-api.md 需要反映 checkout/refunds/message_cards 新端点
- 阈值 0.42/0.62 口径需统一说明

要求：
1. 按实际代码与 git log 更新 project-status.md 的阶段状态与最后更新时间；
2. 更新 resume-evidence.md 的 commit/GitHub 状态，并把最新评测数字（P0 修复后）替换旧数字；
3. 更新 README 已知限制表（checkout 流、web 占位页现状）；
4. 在 docs/eval-report.md 增加"修复前后对照"章节，所有数字标注出处命令。

验收：文档里每个数字都能用文档给出的命令复算；不再出现"0 commit""阶段 14 未开始"这类过期表述。
约束：只改文档，不动代码。
```

---

## 附：验收总清单（全部做完后逐项打勾）

- [ ] `docker compose ps`：api / web / postgres / redis / milvus / etcd / minio 全部 healthy
- [ ] `curl -s localhost:8000/ready` 返回 200
- [ ] `uv run ruff check .` 通过
- [ ] `uv run pytest -q` 全绿（≥ 600 passed）
- [ ] `uv run pytest tests/security -q` 全绿（≥ 86）
- [ ] `cd frontend && npm run typecheck && npx vitest --run` 全绿（≥ 124）
- [ ] `uv run python scripts/verify_stage13.py` 0 不一致项
- [ ] `uv run python scripts/check_deploy_security.py` 34 PASS
- [ ] 检索语料 ≥ 400 chunk，孤儿 chunk = 0
- [ ] 业务评测任务成功率显著高于 0.6324，严格拒答率不再是 0/7
- [ ] 对话页可多选知识库、可调温度/topP/max_tokens/历史轮数
- [ ] `git status` 干净，README/docs 数字与实际一致
