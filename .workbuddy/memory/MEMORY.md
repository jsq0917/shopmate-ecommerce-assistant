# ShopMate 项目长期笔记

## 项目约定（AGENTS.md）
- 开工先读 `AGENTS.md`；按阶段推进，未经确认不跳阶段。默认**不提交 Git**、**不启停/重建容器**。
- 联调用本机 uvicorn 连容器内 PG/Redis/Milvus；改后端业务规则需明确授权。
- 铁律：修复只许改文档表述以服从 `verify_stage13.py`，不许改数字或评测口径。

## 阶段状态
- 阶段 1–10：后端完成。阶段 11（前端）、12（测试/安全）、13（评测）、14（部署）、15（简历/面试材料）：均 PASS。
- **阶段 16（收尾）：完成**（2026-10-20）。
  - Git 基线 `f81159b` + `1bae45d`；**阶段 16 的 30 个文件未提交**（需所有者确认）。
  - 迁移 head `20261020_0005`（handoff 加 `resolution_summary`/`close_reason`；新表 `support_quality_labels`）。
  - 新增 `api/support.py`、`db/repositories/support.py`、`rag/ingest/worker.py`；admin 补上传 / chunk PATCH+DELETE / reindex。
  - 权限：客服端点用 `support:ticket:read|write` 等；**admin 默认无 `support:*` → 403**（契约要求）；会话取证须有授权工单，否则 404。
  - 上传返回 202 + `ingestion_jobs(queued)`；无 BGE-M3 的进程里 job 停在 `queued`——**不要写"已解析"**。
  - fail-open 已修：`policy_qa.sentinel_of()` 归一化（剥 `[cN]`/空白/句末标点、忽略大小写），必须在 unknown-label 检查**之前**；回归 `tests/unit/test_policy_sentinel.py`（7 个 test）。全量评测未重跑。

## 关键数字（阶段 13 原始结果 `stage13-20261020T013230Z.json`）
- 数据集：业务 **136 条 / sha `7606cfce…`**、检索金标 **58 条 / sha `856f3338…`**；pytest 后 sha 不变。
- 检索：R@1/3/5/10=1.00、MRR=1.00、ctxP 0.8459、行为 0.9828（误答 0/误拒 1=exact-05）；引用精度 0.2664→0.3090、片段 6.22→5.03；
  **hybrid vs dense-only 无差异 → 禁止写"提升召回"**；门槛 0.62（dev/test 各 29 条）。
- 业务：意图 0.7059（96/136）、工具 0.6691、任务成功 0.6324（86/136）、严格拒答 0/7、宽松 4/7、越权 8/8、转人工 0.8182(9/11)/精确 1.00、泄漏 0、注入 11/11。
- 延迟：聊天轮 25.63/43.10ms（n=109）、政策检索轮 153.61/202.32ms（n=18）、首 token 24.99/42.39ms（n=107）。
- 压测：**23.0833→29.6058 req/s（+28.3%，取 CSV Aggregated 行）**，P95 570→2400ms，失败 0/1350 与 2/1762。
- 政策答案（本地 qwen2.5:7b，36 条）：**answered 5 / handoff 4 / refused 27**；`refused 27 = 门槛 7 + 模型自判 20`；
  `handoff 4 = uncited_claim`，**不属 refused**；可答 5/29、无答案拒答 7/7、引用合规 5/5、faith 0.88、relevancy 0.52、token 77,709/0 USD。
- 索引规模：PG 48 chunk 行 / 21 ready 版本；Milvus `count(*)` 28，交集 27，孤儿 1，21 行未索引 → 口径要写「27 条有效向量」。
- 门禁（2026-10-20 实测）：ruff 通过 / pytest **638 passed 2 skipped** / security 86 / vitest 124(14 files) / typecheck 0 / verify 0 不一致 / check_deploy_security 34 PASS。

## 反复踩的坑
- **评测集会被 seed 覆盖**（已修）：`synthetic/writers.py::write_eval_cases` 改为「存在且非空则不覆盖」，`test_seed_data` 断言 `>= 100`。
- 冲突夹具会污染其他用例；Locust 只记响应头，SSE 首 token 要自测；延迟必须按 `latency_kind` 分桶。
- Compose v5 `pids_limit` 与 deploy limits 冲突；nginx `server_tokens` 必须放 http 块；`TRUSTED_HOSTS` 必须含 `127.0.0.1,localhost`（否则容器探针 400 → api 永久 unhealthy）。
- 生产栈空库登录 500 → 先 `run --rm seed` + `demo_accounts.py`；Git Bash 跑容器内脚本要加 `MSYS_NO_PATHCONV=1`。

## 联调环境
- 端口：`8000` 被 System 占、`18000` 旧 api 镜像、`18001` 旧 uvicorn；**用 18002/18003**。起后端后 `curl /openapi.json` 确认路径数。
- **Redis 在 16379**（6379 被 milvus-redis 占）：本机后端必须 `REDIS_URL="redis://:change-me-local-only@localhost:16379/0"`。
- `.env` 已存在（已 gitignore），指向 DeepSeek：`deepseek-v4-flash`（`deepseek-chat`/`reasoner` 已弃用），base_url 不带 `/v1`；改后要重启后端。
- 演示账号口令是哨兵哈希，**必须**先跑 `scripts/demo_accounts.py`。
- E2E：`playwright.config.ts` 用 `channel: 'msedge'`；勿 `playwright install chromium`（超时）；跑前清 5173 残留 vite；
  `frontend/e2e/fixture.mjs` 幂等造数据（`e2e.shopper@example.invalid`），退货 spec 的 `beforeAll` 自动跑。
- 验证码是算式题，读取前必须 `expect(question).toHaveText(/\d+\s*\+\s*\d+/)`；多用例 e2e 要 `RATE_LIMIT_AUTH_PER_MINUTE=1000`。

## 前端 UI 约定
- `frontend/src/main.ts` **必须**保留 `import 'element-plus/dist/index.css'`（在 `./style.css` 之前），否则图标裸 SVG 撑满容器。
- 需要 `app.use(ElementPlus, { locale: zhCn })`；组件按需 import，不依赖全局注册。
- 备份：`.workbuddy/backup/ui-icons-20261020-1540/`。

## 简历交付（2026-10-20 晚）
- 已把 ShopMate 项目经历写入 `F:\大模型应用开发\李欣祥_简历.docx`（插到「项目经历」第 1 条），并追加附录 A（证据表 / 定稿文案 / 10 个面试追问 / 不能写进简历的内容）。
- 原件备份 `李欣祥_简历.backup-20261020.docx`；写入用 python-docx 克隆原段落模板以保证字体字号色值一致；表格列宽须同时写 `tblGrid` 与 `tcW`。
- 新数字：后端 638 passed（文档里 600 是阶段 15 口径），`docs/resume-evidence.md` §3/§4.5 仍是 600，未改。
- 简历口径红线：不用 82%/42%/70%/18%；不写"混合检索提升召回"；不写"政策问答准确率 88%"；不写"RAGAS 指标"；越权必须带 8/8 分母；E2E 16 条未复跑不能写"全部通过"。

## 已知缺口（阶段 16 后）
- 意图路由长尾漏判（36 条政策类仅 16 条进 RAG，严格拒答 0/7）；`PRODUCT_FACT` 并入搜索分支（9 条）；商品对比只认 UUID（12 条）；退货链拿不到 `order_item_id`（11 条）；证据门槛单一相似度（1 条误拒）。
- 官方 `ragas` 未跑；结构化 faithfulness/relevancy 未逐轮落盘；`/metrics`、自动备份、多副本扩展缺失。
- Milvus 三卷端到端恢复、docs/09 §7 全量烟测（7.1–7.14）、全新主机从零复核未做。
