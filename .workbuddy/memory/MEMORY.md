# ShopMate 项目长期笔记

## 项目基本约定（来自 AGENTS.md）
- 执行前先读 `AGENTS.md`；按阶段推进，未经确认不跳阶段。
- 默认**不提交 Git**、**不重启/重建/删除 Docker 容器**（0.6），后端联调用本机 uvicorn 进程连容器内 PG/Redis/Milvus。
- 职责边界：各阶段只做本阶段范围；改后端业务规则需明确授权。

## 阶段进度
- 阶段 1-10：后端已完成并通过（阶段 10 记录见各会话）。
- **阶段 13（评测/RAGAS/压测）：D1–D4 整改完成，可判 PASS（待所有者复核，2026-10-20 09:40）。**
  - 历史：2026-10-20 09:00 只读验收为 CONDITIONAL PASS，4 个阻断项已于同日整改并复算一致。
  - **D1 根因（重要）**：`synthetic/writers.py::write_eval_cases` 原先**无条件重写**
    `data/eval/eval_questions.jsonl` 为生成的 100 条，而 `scripts/seed.py` 与 4 个集成测试都调用
    `write_source_files()` → 每次 pytest/seed 都把阶段 13 手写的 36 条删掉。**这是"报告 136 / 磁盘 100"
    反复出现的真正原因**。已改为「文件存在且非空则不覆盖」，`test_seed_data.py` 两处 `== 100` → `>= 100`；
    pytest 之后 sha 不变（实测）。以后再加用例不必担心被 seed 覆盖。
  - 现状口径：业务集 **136 条 / sha `7606cfce…`** + 检索金标 **58 条 / sha `856f3338…`**；
    权威原始结果 `stage13-20261020T013230Z.json`（含 `index` 索引快照、`latency_kind`、`first_delta_ms`）。
  - 关键数字：R@1=1.00（50 金标）/ ctxP 0.8459 / 行为 0.9828 / 误答 0 / 误拒 1（exact-05）；
    引用精度 0.2664（optimised 0.3090）、片段 6.22→5.03；**双路 vs dense-only 无差异（不可写"提升召回"）**；
    业务：意图 0.7059（96/136）、工具 0.6691、任务成功 0.6324（86/136）、严格拒答 0/7、宽松 4/7、
    越权 **1.00（8/8）**、转人工 0.8182(9/11) / 精确 1.00、泄漏 0、注入 11/11；
    延迟：聊天轮 **25.63/43.10ms（n=109）**、政策检索轮 **153.61/202.32ms（n=18）**、首 token 24.99/42.39ms（n=107）；
    压测：**23.08→29.61 req/s（+28.3%，取 CSV Aggregated 行）**，P95 570→2400ms。
  - 政策答案（本机 Ollama qwen2.5:7b，与业务同一 sha）：**36 条** → answered 5 / handoff 4 / refused 27；
    可答 0.1724（5/29）、无答案拒答 1.00（7/7）、引用合规 1.00、faith 0.88、relevancy 0.52、
    token 77,709 / 0 USD、P50 1373.22ms；拒答拆解 门槛 7 / 模型自判 20 / 未标注引用 4。
  - **独立复算**：`scripts/verify_stage13.py`（不 import 评测脚本，从 records 重算全部头条指标 + 数据集指纹对账，
    不一致退出码 1）。**以后改报告数字必须先跑它。**
  - **仍待授权**：`rag/policy_qa.py` 的 `NO_EVIDENCE`/`CONFLICT` 精确比对 fail-open（eval-058/061 实证），
    修法见报告 2.9.0，本轮未动。
  - 数据集有**重建字段**（eval-101…136 的 `reference_answer`、eval-107…110 的 `history`），已在报告 2.2/2.11 标注；
    `multi_turn` 意图 0.75→1.00 的 +1 来自 history 重建，不是系统改动。
  - 未运行：官方 `ragas` 包；结构化 faithfulness/relevancy 代理未落盘逐轮（须重跑脚本复现）。
  - 门禁：ruff 通过 / pytest **587 passed 2 skipped**（与阶段 12 基线一致）/ verify 0 不一致项。
  - 报告 `docs/eval-report.md` 第 2 章（2.14 为整改对照）；状态 `docs/project-status.md` §21。
  - 教训：**评测数据集会被 seed 覆盖**（已修）；冲突夹具会污染其他用例；Locust 只记响应头，SSE 首 token 要自测；
    延迟必须按轮次类型分桶，否则 P95 无意义。
- **阶段 12（测试/安全/故障演练）：PASS（2026-10-20 验收后修复完成）。**
  首次验收为 CONDITIONAL PASS；验收清单 4 项（1×P2 + 3×P3）已于 2026-10-20 全部关闭：
  A 已退款/已退货口径（**含 1 处业务规则变更**：`find_active_return` 把 `completed` 也视为阻断记录）、
  B 报告摘要 15/3/1、C admin RBAC 5→8 条、D 日志提示词标记 +3。
  门禁实测：ruff 通过 / pytest **587 passed 2 skipped**（收集 589）/ security 86 / typecheck 0 /
  vitest 124 / playwright 16 / compose config 通过。后端 576→587（+11，无删除）。
  报告：`docs/test-report.md`（§11 为本次修复）；状态：`docs/project-status.md` §20.6；
  过程记录：`.workbuddy/memory/2026-10-20.md`「阶段 12 验收后修复（完成）」。
- **阶段 11（Vue 3 前端）：已修复完成，2026-10-20 四项门禁全绿（typecheck 0 错误 / vitest 118 / build / Playwright 15/15），可进入阶段 12**（待所有者确认）。
  - 修复详情（4 个根因 + 修法）：`docs/project-status.md` §19；过程记录 `.workbuddy/memory/2026-10-20.md`
  - 修复的 4 个根因：
    1. `client.ts` token 非响应式 → `isAuthenticated` computed 缓存 false → 登录后被弹回登录页。已改 `shallowRef`。
    2. `LoginView.vue` catch 先赋 error 再 `await loadCaptcha()`（其首行清空 error）→ 登录失败无提示。已改「先算 error 再回填」。
    3. e2e 假通过断言 + 验证码竞态（掩盖 1）→ 已收紧为 `.sm-composer-input` 可见 + 等待题目就绪。
    4. **后端登录 cookie `Path=/api/v1/auth`** → 页面读不到 CSRF cookie → 静默刷新不发起。已在 vite 代理与 `web/nginx.conf`（`proxy_cookie_path`）重写 path 兜底；建议阶段 12 后端源头改 `/`。

- **阶段 14（生产部署/文档/演示）：整改完成，2026-10-20 10:58 复评 PASS，可进入阶段 15（未开始）。**
  - 生产：`compose.prod.yaml`（`shopmate-prod` 独立卷；仅 web 8080；数据服务/API 不映射宿主端口；
    api/web `read_only`+tmpfs/`cap_drop: ALL`/no-new-privileges/CPU+内存上限；json-file 10MB×3；
    `${API_IMAGE}`/`${WEB_IMAGE}` 必填；`migrate` 一次性服务；`tools` profile 放 seed/ingest）+
    `web/Dockerfile.prod`（node digest → nginx 非 root）+ `web/nginx.prod.conf`（CSP/限流/SSE）+
    `web/shopmate-proxy.inc` + `.env.prod.example`。
  - 门禁实测：ruff 通过；pytest **591 passed 2 skipped**（+4 Host 白名单）；
    `compose.prod.yaml config` OK；`scripts/check_deploy_security.py` **34 PASS/0 WARN/0 FAIL**；
    生产 web 镜像构建成功，临时容器只读+cap-drop 下 healthy（uid 101 nginx），反代链路经 access log 证实。
  - 新增脚本：`check_deploy_security.py`（发布门禁用 `--strict`）、`demo_accounts.py`
    （幂等给 shopper01/support01/admin01 设口令，默认 `ShopMate-Demo-Only-2026`，仅 example.invalid 合成账号）。
  - 新增配置：`TRUSTED_HOSTS`（空=关闭）+ `TrustedHostMiddleware`；测试 `tests/unit/test_trusted_hosts.py`。
  - 文档：README 重写、`docs/README.md`、`08-deployment`、`09-release-checklist`、`demo.md` v1.0。
  - 坑：Compose v5 `pids_limit` 与 deploy limits 冲突（删 pids_limit）；nginx `server_tokens` 必须放 http 块；
    `web/Dockerfile.prod` 上下文须为仓库根；`.gitignore` 要显式 `!.env.prod.example`。
  - 未实现（已写入文档勘误）：`/api/v1/support/*`；admin 上传/reindex/chunk 编辑。
  - **开发栈 `shopmate-api-1` 仍是 2026-10-18 阶段 4 旧镜像**（openapi 仅 /health、/ready），联调前需重建或改用本机 uvicorn。
  - **2026-10-20 10:20 只读验收结论：CONDITIONAL PASS（未通过）**，2 个 P1：
    ① `TRUSTED_HOSTS` 设真实域名后，api healthcheck 打 `127.0.0.1:8000/health` 会被 TrustedHost 判 **400**（已复现）→ api 永久 unhealthy → web 起不来；
    ② README §4 快速开始的开发栈 web 只提供 `web/public` 阶段 4 占位页（实测 :3000），无法按文档登录。
    P2：Milvus 备份只打 `milvus_data`（漏 minio/etcd）；备份命令 `$POSTGRES_USER` 未导出为空；演示退货步骤二次执行 `DUPLICATE_RETURN`；生产 api 容器从未实际启动。
    复现证据：`check_deploy_security.py` 34 PASS、prod/dev `config --quiet` 均 0、`verify_stage13.py` 全一致、Docker 29.8/Compose v5.5.1。
  - **阶段 14 整改已完成（2026-10-20 10:30–10:58）**，详见 `docs/project-status.md` §22.7 与本日日志：
    ① `TRUSTED_HOSTS` 模板/编排默认值都并入 `127.0.0.1,localhost`（**只填域名会让容器探针 400 → api 永久 unhealthy**），
    单测从 4 条增到 9 条（含“仅域名→回环 400”回归）；② README §4.5 改为三条可用路径（5173 dev / 生产前端镜像 8080 / 生产栈）；
    ③ Milvus 三卷备份（etcd/minio/milvus，恢复序 etcd→minio→milvus）；④ 所有 pg 命令改 `exec -T … sh -c '… "$POSTGRES_USER" …'`；
    ⑤ demo.md 新增“演示前重置”（换单 SQL 用列名 `order_no`）；⑥ 生产栈实跑通过（migrate exit 0、7 容器 healthy、8080 登录成功）。
    另做 P3：CI 加 prod config + `--strict`；`ensure_production_secrets()`（production 下拒 `shopmate-dev-` 前缀）；
    `--forwarded-allow-ips` 收敛为内网网段；**生产编排移除 `build:` 段**（只能 `docker build` 或 CI 推送）。
    门禁：ruff 通过 / pytest **600 passed 2 skipped** / security **34 PASS 0 WARN 0 FAIL** / 两份 compose config exit 0。
  - **生产栈空库登录会 500**（`no shop seeded; run scripts/seed.py first`）→ 先 `run --rm seed` + `demo_accounts.py`；
    Git Bash 跑容器内脚本路径要加 `MSYS_NO_PATHCONV=1`。本机 **8000 端口被其他进程占用**（返回 400），联调用 18001/18002。
  - 仍未验证：Milvus 三卷**端到端恢复**（清卷属破坏性，需单独授权）、生产栈 `ingest`、docs/09 §7 全量烟测（7.1–7.14）、私有仓库 push/pull。

## 联调环境技巧（踩过坑，直接复用）
- **浏览器**：`playwright.config.ts` 已切 `channel: 'msedge'` 复用系统 Edge；`npx playwright install chromium` 下载会超时，不要用。
- **本地 API**（18001，本机进程，不动容器）：见 `2026-10-20.md` 的完整命令；务必带 `RATE_LIMIT_AUTH_PER_MINUTE=1000`，默认 10 次/分钟会让多用例 e2e 触发 429。
- **演示数据**：种子库无可登录账号，用 `frontend/e2e/fixture.mjs`（幂等）注册 `e2e.shopper@example.invalid` 并造合成订单/物流/清理退货与工单；产物 `frontend/e2e/.fixture.json`。凭证见 `frontend/.env.example`。退货 spec 的 `beforeAll` 已自动跑 fixture，消除跨轮 `DUPLICATE_RETURN` 污染。
- **验证码**：登录页算式题（服务端签名），正则 `/(\d+)\s*\+\s*(\d+)/` 求和；读取前必须 `expect(question).toHaveText(/\d+\s*\+\s*\d+/)`，否则读到「加载中…」。
- **跑 e2e 前清掉 5173 残留 vite 进程**，否则 playwright `reuseExistingServer` 会复用旧代码实例。

## 阶段 15 状态：**PASS**（2026-10-20 11:45 整改后复核）

- **11:17 首轮只读验收为 CONDITIONAL PASS，唯一阻断项是 `docs/interview-prep.md` Q10 数字拆分错误**
  （写成「27 条 refused 里 7 + 20 + 4」= 31）。**已于 11:24–11:45 整改完毕，阶段 15 判定 PASS，
  可进入最终演示/交付**。记录见 `docs/project-status.md` §23.6 与 `.workbuddy/memory/2026-10-20.md`。
- 正确口径（**永久按这个说**）：`answered 5 / handoff 4 / refused 27`（5+4+27=36）；
  `refused 27 = 门槛拒绝 7 + 模型自判 20`（7+20=27）；`handoff 4 = uncited_claim`（**不属于 refused**）。
  原始结果 `parts.policy_llm.status_counts` 与逐条 `reasons` 均可直接验证。
- 整改 5 条 + 1 条可选（已全部关闭）：Q10 重写；向量口径统一为「27 条有效向量（Milvus `count(*)` 28，含 1 条孤儿）」
  （interview Q3/速查卡、resume §4.1、eval-report 2.4.3/2.9.4、status §23.4）；README §12 补两行索引；
  demo §3.4 补 7B 可答率 5/29 与 `NO_EVIDENCE [c1]` fail-open 两条自检；status §22.5 加"生产栈已实跑"补注；
  可选项未改代码，只在 resume §8 注明单跑 `test_query_rewrite.py` 需先 import knowledge 模块。
- 附带纠错：fail-open 章节引用统一为 `eval-report.md §2.9.0`（原 2.5.2 与 demo 写 2.9.1 #0，找不到依据）。
- **验收实测量（可复现，勿再改动）**：verify_stage13 0 不一致 / EXIT 0；数据集 136/`7606cfce…`、58/`856f3338…`（pytest 后不变）；
  pytest **600 passed 2 skipped**（137.27s，收集 602）；`grep "28 条向量"` 与 `"2.9.1 #0"` 均 0 处。
- **铁律**：修复只许改文档表述以服从原始结果（`verify_stage13.py` 为准），**不许为了对齐而改数字或改评测口径**；
  不改业务规则、不提交 Git、不启停容器。`NO_EVIDENCE` fail-open 仍未修（待所有者授权），已作为已知缺陷写进台账/面试/演示。
- **踩坑提醒**：在整改记录里"原样引用旧表述"会让自检 grep 命中自己；描述旧写法要用断词写法（如「28 条（未标 `count(*)`）」）。

## 已知后端缺口（影响前端页面可用性，非前端缺陷）
- `/api/v1/support/*` 未注册（404）→ 客服工作台页面呈错误态。
- admin 的文档上传 / reindex / chunk 变更端点未注册 → 管理端部分操作不可用。
- 前端均已按 `docs/06-api.md` 契约实现，后端部署后即通。
- 退货/转人工/会话等消费侧链路已实测全通；消费者越权访问 `/admin/*` 后端返回 403。
