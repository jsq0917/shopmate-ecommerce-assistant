# ShopMate 项目状态

> 最后更新：2026-10-23 15:10（Asia/Shanghai；阶段 18–20 收尾，文档与代码/git 对齐）
> 当前阶段：**阶段 0–16 已完成并推送 GitHub；阶段 17 已提交待推送；阶段 18–20 已实现未提交**
> 阶段状态：阶段 13 已 PASS（D1–D4 全部关闭，见 §21、`docs/eval-report.md` 2.14）；
> 阶段 14／15／16 已完成（§22／§23／§24）；阶段 17 补齐结算、退款与客服回复并改版前端（§25）；
> 阶段 18／19／20 见 §26。**阶段 14 早已完成**；16 阶段计划之外的工作（18–20）属课程任务书补齐，
> 是否继续扩展由所有者决定。

## 0. 当前状态速览（2026-10-23，先读这一节）

### 0.1 阶段进度

| 阶段 | 内容 | 状态 | 记录位置 |
|---|---|---|---|
| 0–4 | 环境基线、资料审计、契约、Compose 与骨架 | 完成 | §1–§13 |
| 5–9 | 数据、结构化工具、政策 RAG、路由与安全、订单/退货/转人工 | 完成 | §14–§18 |
| 11–12 | Vue 3 前端、测试与安全 | 完成 | §19–§20 |
| 13 | 评测、RAGAS 与压测 | **PASS**（整改 D1–D4 关闭） | §21、`docs/eval-report.md` 2.14 |
| 14 | 生产部署、文档与演示 | 完成 | §22 |
| 15 | 简历证据与面试材料 | 完成 | §23、`docs/resume-evidence.md` |
| 16 | 最终收尾（客服工单、上传、质检标签） | 完成 | §24 |
| 17 | 结算/支付/取消、退款审核、客服回复、前端设计系统 | 完成（已提交，待推送） | §25 |
| 18 | 对话页知识库多选 | 完成（未提交） | §26.1、`docs/06-api.md` §6.1 |
| 19 | 对话页推理参数面板 | 完成（未提交） | §26.2、`docs/06-api.md` §6.1 |
| 20 | 图片文档 OCR 入库与原图回源（可选扩展） | 完成（未提交） | §26.3、`docs/06-api.md` §6.3 |

### 0.2 Git 与远端（命令可复算）

```bash
cd E:/project/shopmate-ecommerce-assistant
git log --oneline                 # 7 个提交
git rev-list --count HEAD         # 7
git status -sb                    # ## main...origin/main [ahead 3]
git remote -v                     # origin git@github.com:jsq0917/shopmate-ecommerce-assistant.git
```

- **已推送**（`origin/main` 有 4 个提交）：`f81159b` 仓库基线 → `1bae45d` 阶段 0–15 文档
  → `a7b9632` 阶段 16 收尾 → `5978d82` 推送记录。
- **已在本地提交、尚未推送**（3 个）：`28ef24a` 阶段 17 下单支付退款与商品卡片 →
  `23c3516` 结算页/退款页与前端设计系统 → `a19d053` 阶段 17 文档、验收截图与演示脚本。
- **未提交的工作区改动**：阶段 18–20 的全部代码与文档（`git status --short` 可列出，
  含 `api/knowledge_assets.py`、`synthetic/image_render.py`、图片语料与 3 条图片金标）。
- 默认不自行 `git commit` / `git push`（`AGENTS.md` §0.6），提交时机由所有者决定。

### 0.3 读法说明：历史段落里的"仓库无 commit"

§2、§23.2、§23.4 与各阶段完成报告里的"仓库仍无 commit／0 个 commit"是**写那段时的真实状态**
（首次提交发生在 2026-10-21 上午；推送记录见 `5978d82`，提交时间 2026-10-21 11:18）。**现状以 §0.2 为准**，
不要把历史段落当成当前结论。

### 0.4 证据门槛口径（0.42 / 0.62）

- **0.62 是唯一的生产/评测口径**：`.env`、`.env.example`、`compose.yaml`、`compose.prod.yaml`、
  `docs/08-deployment.md` §460 与 `README.md` §7 已全部一致（可用
  `rg -n "POLICY_MIN_EVIDENCE_SIMILARITY" .env.example compose.yaml compose.prod.yaml` 核对）。
- **0.42 只是"宽松演示档"**：用它能让无答案问题也被答出来，实测严格拒答率 7/7 → 0/7，
  因此**任何指标对比都必须用 0.62**；0.42 仅用于现场演示"链路能答"。
- 历史实验（`data/eval/results/intent-fallback-on-gate042-*.json`）就是 0.42 的反例证明，
  见 `docs/eval-report.md` 2.6.1 与新增的 §5。

### 0.5 复算脚本当前输出（2026-10-23 实测）

```bash
uv run python scripts/verify_stage13.py --raw data/eval/results/stage13-deepseek-20261023.json
# → 业务/政策/索引段全部 OK；检索段报 2 项：
#   retrieval.sha256: recomputed=03978693… claimed=5fe76a09…
#   retrieval.cases : recomputed=143       claimed=140
uv run python reconcile_index.py
# → PG 577 chunk 行 / 89 ready 版本 / enabled 431；Milvus 431；交集 431；孤儿 0
```

那 2 项差异来自金标 140 → 143 条（新增 3 条图片用例，见 §26.3），**不是数字造假**；
历史阶段记录里"verify 输出 0 不一致"是各自当时的真实输出。处理方案二选一（重跑 143 条 /
把指纹检查限定为同一数据集）都需要所有者确认，本轮不改代码，详见 `docs/eval-report.md` §5.5。

## 1. 阶段范围与边界

阶段 0 完成只读环境基线检查；阶段 1 完成课程资料、参考项目和 GitHub 仓库审计；阶段 2 与阶段 3 已产出 PRD、安全、架构、数据、工具和 API 契约。阶段 4 本次创建 Compose、容器镜像定义、FastAPI 健康检查骨架、异步数据库与 Alembic 基线、测试和 CI 初稿。

阶段 4 已遵守以下边界：

- 只在项目目录内增量创建脚手架、配置、源码、测试和文档。
- 仅启动本项目 7 个 Compose 容器；未停止或修改既存 `milvus-redis`，未删除任何容器、卷或镜像。
- 执行了获授权的 `docker compose up -d --build`；未执行 `docker compose down`、prune、`git commit`、`git push`、`git reset` 或 `git clean`。
- 未修改 `E:\AI大模型开发\eduRAG(陈杰老师)` 下的任何内容。
- 未安装或修改 Docker Desktop 配置。

## 2. 工作目录与 Git 基线（阶段 0 快照）

> **这一节是阶段 0 开工时的快照，已过时**。当前提交数、远端与推送状态见 §0.2。

- 工作目录：`E:\project\shopmate-ecommerce-assistant`
- 目录确认：正确。
- 当前分支：`main`
- 提交状态：尚无任何 commit。
- 已跟踪文件：无。
- 当前 Git 状态：所有现有脚手架均为未跟踪文件：

```text
## No commits yet on main
?? .gitignore
?? .python-version
?? AGENTS.md
?? README.md
?? docs/
?? pyproject.toml
?? src/
```

## 3. 工具版本

| 工具 | 实测版本 | 结果 |
|---|---|---|
| Python | 3.12.14 | 通过 |
| uv | 0.12.11 | 通过 |
| Node.js | v24.19.0 | 通过 |
| npm | 11.17.0 | 通过 |
| Git | 2.55.0.windows.2 | 通过 |
| Docker CLI | 29.8.0, build 88096ef | 通过 |
| Docker Compose | v5.5.1 | 通过 |

补充环境事实：

- `python` 当前解析为：`D:\dev\anaconda3\python.exe`
- `uv python find 3.12` 同样解析到上述 Python。
- `SSL_CERT_DIR=D:\dev\anaconda3\Library\ssl\certs`。
- 该证书目录存在，但只有 `.keep` 文件；uv 报告 `No valid certificates found`。
- 后续应优先使用 `uv run`，让项目环境与全局 Python 隔离。

## 4. Docker 状态

### 4.1 阶段 0 历史快照

以下内容是阶段 0 检查时的历史记录，不代表 2026-10-18 22:09 的当前状态。

阶段 0 执行 `docker info` 成功，退出码为 0。

关键输出：

- Server Version：29.8.0
- Operating System：Docker Desktop
- OSType：linux
- Architecture：x86_64
- CPUs：32
- Total Memory：15.52 GiB
- Docker Root Dir：`/var/lib/docker`

结论：

- 阶段 0 检查时，Docker Desktop 已运行，不需要用户另行启动。
- 阶段 0 检查时，Docker 使用 Linux containers。

阶段 0 检查时已有以下运行中资源和端口占用：

- 容器 `milvus-redis` 正在运行，镜像为 `redis:7.2`。
- `6379` 端口已由该 Redis 容器映射并监听。
- `8000` 端口已有监听项，进程 ID 为 4。
- 本阶段未停止、重启或修改上述容器和端口配置。

### 4.2 阶段 1 修复时只读复验

2026-10-18 22:09 只读执行：

```powershell
docker --version
docker compose version
docker info
docker ps
```

结果：

- Docker CLI 仍为 29.8.0，Docker Compose 仍为 v5.5.1。
- `docker info` 退出码为 1，报错显示无法连接 `dockerDesktopLinuxEngine`。
- `docker ps` 退出码为 1，无法读取容器列表。
- 本次没有启动 Docker Desktop，没有启动、停止或删除容器/卷，也没有修改 Docker 配置。

因此，阶段 1 修复时只能确认 Docker daemon 当前不可连接；阶段 4 启动基础设施前必须重新检查，未获用户明确同意不得启动或操作现有容器。

### 4.3 阶段 4 只读复验

2026-10-18 22:50 左右重新执行：

```powershell
docker --version
docker compose version
docker info
```

结果：

- Docker CLI：29.8.0，build 88096ef。
- Docker Compose：v5.5.1。
- Docker daemon 可用，使用 Linux containers、amd64、32 CPU、15.52 GiB memory。
- 本阶段仍未执行 `docker compose up`、`down`、容器删除、卷删除或镜像清理。

23:00 左右的端口只读检查显示 `6379` 和 `8000` 已有监听项。启动本项目前需要确认端口冲突或调整 `.env`，不得停止用户现有进程。

## 5. 现有脚手架

| 路径 | 当前状态 | 说明 |
|---|---|---|
| `AGENTS.md` | 存在 | 项目级权威执行合同，已完整读取 |
| `.gitignore` | 存在 | 已覆盖密钥、Python、测试、前端、IDE 和 OS 生成文件 |
| `.python-version` | 存在 | 内容为 `3.12` |
| `pyproject.toml` | 存在 | uv 项目；已声明运行时/开发依赖和 Ruff、pytest 配置 |
| `README.md` | 存在但为空 | 尚无可复现的启动说明 |
| `src/shopmate_ecommerce_assistant/` | 存在 | FastAPI 应用工厂、配置、健康检查、异步 SQLAlchemy 骨架 |
| `uv.lock` | 存在 | 已锁定运行时和开发依赖 |
| `compose.yaml` | 存在 | 7 个服务、5 个 named volumes、全部服务 healthcheck |
| `.env.example` | 存在 | 端口、依赖连接和安全占位符；不包含真实凭据 |
| `Dockerfile` | 存在 | API 多阶段构建、代码 COPY、非 root、无 reload |
| `web/` | 存在 | 阶段 4 非 root Nginx 静态占位页与 healthcheck |
| `docs/project-status.md` | 本阶段创建 | 当前状态文档 |
| `alembic/`、`alembic.ini` | 存在 | async SQLAlchemy Alembic 环境与单一空基线迁移 |
| `tests/` | 存在 | 健康检查、安全失败响应与 Alembic head 单元测试 |
| `.github/workflows/ci.yml` | 存在 | Ruff、pytest 和 Compose config 初稿 |

`pyproject.toml` 当前事实：

- 包名：`shopmate-ecommerce-assistant`
- 版本：`0.1.0`
- Python 要求：`>=3.12`
- 运行时依赖：FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy async、asyncpg、Redis、httpx、Alembic
- 开发依赖：pytest、pytest-asyncio、Ruff
- 已配置 CLI 入口：`shopmate_ecommerce_assistant:main`
- 已配置 `uv_build` 构建后端。
- 存在作者邮箱元数据。该字段不是密钥，但发布前应确认是否保留。

运行时和开发依赖均通过 `uv add` 写入并生成 `uv.lock`。

## 6. 密钥、路径与依赖检查

阶段 4 对新增配置、镜像定义、环境模板和 Python 源码执行了凭据、绝对路径、特权容器与 Docker socket 检查：

- 未发现 credential-like 赋值。
- 未发现常见 API Key、云访问密钥或私钥前缀。
- Compose 构建上下文使用相对路径；容器内部连接使用服务名或容器内路径。
- `.env.example` 只包含本地占位值，`.env` 当前不存在。
- 未发现代码引用尚未声明的第三方依赖。
- 未发现 `privileged: true`、Docker socket 挂载或 `latest` 镜像。

阶段 4 已处理：

1. `.gitignore` 已忽略 `.env`、日志、缓存、测试产物、`node_modules` 和常见 IDE/OS 文件。
2. `pyproject.toml` 描述已改为项目名称，依赖与质量工具配置已落地。
3. `uv.lock` 已生成。
4. `.env` 当前不存在，只存在安全占位模板 `.env.example`。

仍需处理：

1. `README.md` 需要在后续文档阶段补全启动、迁移和演示说明。
2. `SSL_CERT_DIR` 指向的目录没有有效证书文件；本次通过可访问的 HTTPS 包源完成本地安装，未修改系统证书。

## 7. 路径权限与只读边界

- 项目目录：阶段 0 的 ACL 检查显示当前环境具备修改权限；当时创建 `docs/project-status.md` 也验证了项目目录可写。
- 参考目录 `E:\AI大模型开发\eduRAG(陈杰老师)`：
  - 目录存在。
  - ACL 显示 `CodexSandboxUsers` 和 `Authenticated Users` 具有 `Modify` 权限。
  - 因此该目录在文件系统层面并非强制只读；当前只读性依赖 AGENTS.md 的执行约束。
  - 本阶段未在参考目录写入、删除或修改任何内容。

风险结论：若需要操作系统级只读保护，应在用户明确授权后单独评估 ACL 加固方案，不得在本阶段自行修改。

## 8. 阶段 0 验收

| 验收项 | 结果 | 证据 |
|---|---|---|
| 项目根目录正确 | 通过 | `Get-Location` 输出目标路径 |
| 参考目录未被修改 | 通过 | 本阶段仅执行只读命令 |
| 项目目录可写 | 通过 | 成功创建本状态文档 |
| 未启动容器 | 通过 | 未执行任何 `docker compose up/start` |
| 未修改业务代码 | 通过 | Git 状态仍仅显示原有未跟踪脚手架及新增 `docs/` |
| Docker Desktop 是否需要启动 | 不需要 | `docker info` 成功 |
| 环境版本可记录 | 通过 | 第 3 节实测版本 |
| 风险和冲突已记录 | 通过 | 第 4、6、7 节 |

## 9. 验证命令

```powershell
Get-Location
git status --short --branch
Get-Content -LiteralPath 'docs/project-status.md'
```

## 10. 已知风险与后续建议

- 2026-10-18 23:00 左右的只读端口检查显示 `6379` 和 `8000` 已有监听项。阶段 4 未停止或修改这些进程；启动本项目前必须调整 `.env` 端口或由用户明确处理冲突。
- 下载依赖前应处理 `SSL_CERT_DIR` 的有效证书问题，或在不修改系统配置的前提下使用项目级可复现方案。
- 参考目录的只读边界未由 ACL 强制执行，必须继续依赖 AGENTS.md 的人工和代理约束。
- 当前仓库尚无首次 commit，暂无可用于回滚的 Git 基线；未经用户明确同意不得提交。

## 11. 阶段 1 产出与验证

本阶段新增：

- `docs/00-course-distillation.md`：课程 RAG 实战、RAG 讲义、电商智能客服场景和本地参考工程的可借鉴点、来源矩阵、冲突点与禁止照搬项。
- `docs/01-audit.md`：当前脚手架与参考项目只读审计、三通道架构初稿、10 类意图映射和风险。
- `docs/01-github-research.md`：四个 GitHub 参考仓库的 commit、许可证、可借鉴模块和禁止复制项。
- `docs/resume-evidence.md`：按 `AGENTS.md` 第 22 节建立简历与面试证据台账，明确当前尚无业务实现、测试和量化结果。

只读验证包括：

- 参考项目目录结构与关键文件读取。
- `EduRAG_V7.5讲义` 六个相关目录的关键主题和代表性 HTML 文件读取。
- 电商智能客服场景 HTML 的产品旅程、风险边界和示例指标读取。
- `Itcast_qa_system` 的 Git 元数据、许可证文件名扫描、测试/CI 目录扫描和 Docker 风险审阅。
- GitHub License API、commit API 和仓库树元数据核验。
- 未执行 `docker compose up/down`、容器删除、容器停止或 Docker 配置修改。
- 未修改业务代码，未在参考目录写入内容，未执行 Git commit/push/reset/clean。

阶段 1 验收缺口修复仅更新 `docs/00-course-distillation.md` 和本状态文档：补充 RAG 讲义与电商场景来源、逐项借鉴点、宣传数字和真实 PII 禁止项，并把历史 Docker 状态与阶段 1 修复时的只读复验结果区分。业务代码、参考目录和 Git 历史未修改。

## 12. 阶段门禁

- 阶段 0：已完成。
- 阶段 1：产出已存在。
- 阶段 2：PRD、MVP、安全与演示文档已产出。
- 阶段 3：架构、数据、工具、API 契约与 ADR 已产出。
- 阶段 4：验收通过。
- 阶段 5：实施完成并自测通过（见第 14 节），待用户验收。
- 阶段 6：实施完成并自测通过（见第 15 节），待用户验收。
- 阶段 7：**验收通过**（见第 16 节，含 D1–D5 整改与 D5 口径确认）。
- 阶段 8：**验收通过**（见第 17 节，含 17.10 的 G1–G8 验收缺陷修复）。
- 阶段 9：**验收通过**（见第 18 节，含 18.7 的 D1/D2 整改）。

## 13. 阶段 4 实施与验证记录

### 13.1 镜像基线与验证方法

Compose 中所有第三方镜像均使用固定 tag + digest：

| 服务 | 固定镜像 |
|---|---|
| API 构建 | `python:3.12.14-slim-bookworm@sha256:392307...3564e` |
| Web 构建 | `nginx:1.27.5-alpine@sha256:65645c...f2a10` |
| PostgreSQL | `postgres:16.9-bookworm@sha256:253815...5be94` |
| Redis | `redis:7.2@sha256:063795...6773c` |
| etcd | `quay.io/coreos/etcd:v3.5.5@sha256:b83c1d...f3a4` |
| MinIO | `minio/minio:RELEASE.2023-03-20T20-16-18Z@sha256:6d770d...3b93` |
| Milvus | `milvusdb/milvus:v2.4.4@sha256:212ec3...dcfa7` |

验证方法：

1. `docker pull <tag>` 成功；已有本地镜像直接使用 `docker image inspect` 核验。
2. `docker image inspect ... --format '{{join .RepoDigests ","}}'` 输出上述 digest。
3. `docker compose config --images` 再次列出固定镜像引用。

Python、Nginx、PostgreSQL 为实际拉取验证；其余镜像为本机已有固定版本。项目本地构建镜像固定为 `shopmate-api:0.1.0` 和 `shopmate-web:0.1.0`，Compose 不再引用 `latest`。

### 13.2 服务与健康检查

`docker compose config` 通过。解析结果确认：

- 服务：`api`、`web`、`postgres`、`redis`、`etcd`、`minio`、`milvus`。
- 全部 7 个服务都有 healthcheck。
- `postgres`、`redis`、`etcd`、`minio`、`milvus` 都有 named volume。
- `milvus` 等待 `etcd`、`minio` 健康；`api` 等待全部基础设施健康；`web` 等待 `api` 健康。
- 未配置 Docker socket、`privileged` 或 `latest`。
- Compose 路径使用相对构建上下文；运行时容器地址使用服务名和容器内路径。

API 容器使用非 root UID/GID `10001`，默认命令先执行 `alembic upgrade head`，再以无 reload 模式启动 Uvicorn。Web 使用非 root Nginx 用户监听容器内 `8080`。

### 13.3 本地测试证据

执行的命令与结果：

```text
uv run ruff check .                    -> All checks passed
uv run ruff format --check .           -> 31 files already formatted
docker compose config --quiet          -> exit 0
uv run pytest                          -> 5 passed, 1 third-party deprecation warning
uv run alembic heads                   -> 20261018_0001 (head)
docker build --check -f Dockerfile .   -> no warnings
docker build --check (web context)     -> no warnings
docker compose up -d --build           -> 7 services started
docker compose ps                      -> 7 services running/healthy
/health                                -> HTTP 200 {"status":"ok"}
/ready                                 -> HTTP 200, postgres/redis/milvus all ok
web /healthz                           -> HTTP 200 "ok"
```

测试覆盖：

- `/health` 在依赖不可用时仍返回 200。
- `/ready` 在 PostgreSQL、Redis、Milvus 全部健康时返回 200。
- 依赖部分失败或检查器抛异常时返回 503。
- 失败响应不泄露连接串或异常文本。
- Alembic 只有一个基线 head。

### 13.4 运行验收证据

为避免影响既存 `milvus-redis` 和宿主 `8000` 服务，本次使用：

```text
API_PORT=18000
WEB_PORT=3000
REDIS_PORT=16379
POSTGRES_PORT=5432
MILVUS_PORT=19530
MILVUS_METRICS_PORT=9091
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
```

实际结果：

- `shopmate-api-1`、`shopmate-web-1`、`shopmate-postgres-1`、`shopmate-redis-1`、`shopmate-etcd-1`、`shopmate-minio-1`、`shopmate-milvus-1` 全部为 running/healthy。
- API 容器 UID/GID：`10001:10001`；Web 容器 UID：`101`。
- API 日志无未处理堆栈、连接串、密码或 token；Alembic 基线迁移成功。
- 5 个 named volumes 均已挂载到对应服务。
- 所有容器 `HostConfig.Privileged=false`，无 Docker socket 挂载。
- `.env` 不存在且被 `.gitignore` 忽略；未提交或暂存任何文件。
- `uv sync --frozen`、Ruff、格式检查、5 个 pytest 和 Alembic head 检查全部通过。

阶段 4 验收通过，可以进入阶段 5。阶段 5 的实施与验证见第 14 节。

## 14. 阶段 5 实施与验证记录

### 14.1 边界遵守

- 只写入项目目录：`src/`、`scripts/`、`tests/`、`alembic/`、`data/`、`docs/`。
- 未启动、重启、停止任何容器；未删除任何容器、卷或镜像；仅对 `shopmate-postgres-1` 执行只读 `psql` 查询。
- 未执行任何 Git 写操作（`add`/`commit`/`push`/`reset`/`clean`）；仓库仍无 commit。
- 未开始商品搜索 UI、订单 API 或任何阶段 6 之后的实现。

### 14.2 新增代码与数据文件

| 路径 | 作用 |
|---|---|
| `src/.../core/paths.py`、`core/ids.py` | 数据目录常量；`stable_uuid()` 稳定主键命名空间 |
| `src/.../db/models/{enums,columns,catalog,orders,knowledge}.py` | 12 个枚举、16 张表模型 |
| `alembic/versions/20261019_0002_stage5_data_and_knowledge.py` | 建表、索引、复合唯一约束 |
| `src/.../synthetic/catalog_data.py`、`knowledge_corpus.py`、`eval_cases.py`、`writers.py`、`seed.py` | 固定 seed 的合成数据集与多格式渲染 |
| `src/.../rag/chunking.py`、`embeddings.py`、`errors.py`、`milvus_store.py` | 父/子分块、确定性 embedding、向量库封装 |
| `src/.../rag/ingest/{loaders,manifest,pipeline}.py` | PDF/DOCX/PPTX/MD/TXT 解析、清单校验、入库流水线 |
| `scripts/seed.py`、`scripts/ingest.py` | 两个 CLI，均支持 `--json` |
| `tests/unit/test_{chunking,loaders,embeddings}.py`、`tests/integration/test_{seed_data,ingestion,milvus_store}.py` | 单元与集成测试 |

生成的数据（`data/`，全部标记 synthetic）：

- `data/knowledge/policy/`：21 份政策文档 — 14 × MD、2 × PDF、2 × DOCX、2 × TXT、1 × PPTX。
- `data/knowledge/manifest.json`：21 条来源规格（版本、生效期、地区、店铺、知识库）。
- `data/knowledge/faq.jsonl`：50 条 FAQ。
- `data/eval/eval_questions.jsonl`：100 条评测问题。
- `data/synthetic/`：商品/订单快照与数据集指纹。

### 14.3 seed 数据集与幂等

`scripts/seed.py` 使用 `SEED=20261019`，所有主键由 `stable_uuid` 派生，写入统一走 `ON CONFLICT DO UPDATE`。

| 表 | 行数 |
|---|---|
| shops | 1 |
| users | 14 |
| products | 30 |
| product_variants | 48 |
| inventory | 48 |
| promotions | 4 |
| orders | 100 |
| order_items | 156 |
| shipments | 65 |
| shipment_events | 230 |
| knowledge manifest 条目 | 21 |
| FAQ | 50 |
| 评测问题 | 100 |

- 数据集指纹：`67e40fa7-38b9-527f-a368-c3bf2f81a0bd`（三次连续执行一致）。
- 连续重复执行 `scripts/seed.py --json` 三次，上述行数与指纹完全一致，无重复行。
- 所有业务表带 `is_synthetic = true`；用户邮箱统一使用 `.invalid` 保留域，不含真实 PII。

### 14.4 分块与元数据

- 父块目标 1500 字符、子块目标 480 字符（`settings.parent_chunk_chars` / `child_chunk_chars`）；均衡分组避免产生过短尾块。
- 子块保留 `heading_path`（标题路径）、`page_no`（PDF/PPTX 页码）、`parent_id`、`token_count`、`content_hash`。
- 版本层保留 `version`、`effective_from/effective_to`、`region`、`locale`、`shop_id`、`knowledge_base_id`、`source_uri`、`mime_type`。
- 只有子块写 Milvus（`is_enabled = true`）；父块留在 PostgreSQL 供后续引用扩展。

### 14.5 Milvus collection 与检索过滤

- Collection：`shopmate_knowledge_chunks`，维度 384，`AUTOINDEX` + `COSINE`，主键 `chunk_id`。
- 标量字段：`shop_id`、`knowledge_base_id`、`document_id`、`version_id`、`doc_type`、`locale`、`region`、`status`、`is_enabled`、`effective_from/to`、`page_no`、`heading_path`、`text`、`metadata_json`。
- 检索表达式同时约束租户、知识库、地区、文档类型与生效窗口（`effective_from <= at < effective_to`，空 `effective_to` 记为 0 表示长期有效）。
- embedding 采用确定性 feature hashing（CJK 单字 + bigram + 拉丁词 + L2 归一化），离线可复现；后续接入真实 embedding 模型只需替换 `EmbeddingProvider`。

### 14.6 失败处理

- 元数据（知识库 / 文档 / 版本 / ingestion job）先写入并 commit，再读取文件，因此文件缺失或损坏也会留下 `failed` 记录。
- 错误码：`FILE_NOT_FOUND`、`PARSE_FAILED`、`UNSUPPORTED_DOCUMENT_TYPE`、`DOCUMENT_TOO_LARGE`、`EMPTY_DOCUMENT`、`UNSAFE_SOURCE_PATH`、`UNEXPECTED_ERROR`。
- 失败时清理该版本已写入的 PostgreSQL 片段与 Milvus 向量，`ingestion_jobs.error_code` 与 `knowledge_versions.failure_code` 同时记录安全文案（截断 500 字符，不含绝对路径与堆栈）。
- `ingestion_jobs` 每次尝试生成一行，`attempt_count` 递增，重跑成功不删除历史尝试记录。

### 14.7 验证证据

```text
uv run ruff check .                      -> All checks passed
uv run ruff format --check .             -> 79 files already formatted
uv run alembic heads                     -> 20261019_0002 (head)
uv run pytest                            -> 48 passed, 2 third-party warnings
uv run pytest tests/unit                 -> 28 passed
uv run pytest tests/integration/test_milvus_store.py -> 6 passed
uv run pytest tests/integration/test_ingestion.py    -> 7 passed
uv run python -u scripts/seed.py --json  -> 30 商品 / 100 订单 / 21 文档 / 50 FAQ / 100 评测
uv run python -u scripts/ingest.py       -> 完成：21 个版本 ready，0 个失败
```

数据库与向量库实测（只读查询）：

```text
knowledge_documents = 20, knowledge_versions = 21, ready = 21
knowledge_chunks    = 48（父 21 / 子 27）
milvus rows         = 27（与子块数一致，重跑后仍为 27）
```

`scripts/ingest.py` 连续重跑两次：`knowledge_chunks` 的 id 指纹稳定为 `c8cfbc7117fe7bd85bc415fd08c730f8`，行数保持 48/27，`ingestion_jobs.attempt_count` 由 11 → 12，说明重复入库既不产生重复数据也不产生新片段 ID。

测试覆盖点：

- seed 幂等（两次执行行数一致）、各表数量、`is_synthetic` 标记、邮箱 `.invalid`、订单金额一致性、FAQ 与评测集数量、清单与文件存在性。
- 分块：父子引用、标题路径、尺寸预算、跨父块边界、空文档、确定性分块。
- loader：MD/TXT/PDF/DOCX/PPTX 解析、页码保留、拒绝不支持的扩展名。
- Milvus：schema 字段、写入/检索/删除、生效窗口过滤、地区与文档类型过滤、同 ID upsert 幂等、维度校验。
- ingestion：父子元数据与向量落库、重复入库稳定、过期版本不可检索、地区隔离、缺文件 `FILE_NOT_FOUND`、损坏 PDF `PARSE_FAILED`、路径逃逸 `UNSAFE_SOURCE_PATH`。

### 14.8 已知限制

1. 21 份政策文档中多数短于子块目标 480 字符，因此只有 27 个子块（4 份文档需要多子块）；父/子分块的多块路径由测试中的长文档覆盖。
2. `ingestion_jobs` 累积了调试期间的多次尝试记录（每版本 11～12 次），这是审计设计而非数据重复；如需干净演示环境可重建数据库后再执行一次 seed 与 ingest。
3. embedding 为确定性哈希实现，检索质量只用于验证链路与过滤语义，不代表最终召回效果。
4. `data/`（共 472 KB，其中 `data/knowledge` 420 KB）当前未被 `.gitignore` 忽略，也未提交。合成文件由 `scripts/seed.py` 可复现生成，首次 commit 前需决定是纳入版本库（保证离线可复现）还是忽略并在 README 说明生成步骤。


## 15. 阶段 6 实施与验证记录

### 15.1 边界遵守

- 仅新增/修改 `src/`、`tests/`、`docs/` 下与商品结构化搜索相关的文件；未改动数据库 schema，无新迁移。
- 未接入 RAG 政策问答、订单/物流/退货工具、FastAPI 商品路由和前端。
- 未启动、停止或删除容器；未删除卷或镜像；仅执行只读 SQL 与本地测试。
- 未执行任何 Git 写操作；仓库仍无 commit。

### 15.2 新增代码

| 路径 | 作用 |
|---|---|
| `src/.../core/errors.py` | `ErrorCode` 与 `ToolError`，把失败收敛为稳定错误码 |
| `src/.../domain/catalog/models.py` | 仓储/领域/工具之间传递的纯 dataclass |
| `src/.../domain/catalog/attributes.py` | 受控属性词表白名单、标签、单位、别名与比较维度 |
| `src/.../domain/catalog/search.py` | 中文 bigram 切词、停用词、命中打分与排序、命中原因 |
| `src/.../domain/catalog/compare.py` | 字段对齐的比较行；缺失值 `known=false/value=null/display=unknown` |
| `src/.../domain/catalog/stock.py` | 库存聚合与 `in_stock/out_of_stock/unknown` 判定 |
| `src/.../domain/catalog/ports.py` | `CatalogReader` 协议，便于用假仓储做单元测试 |
| `src/.../db/repositories/catalog.py` | 参数化、全部带 `shop_id` 的只读查询（窗口函数取每商品最低价可售 SKU） |
| `src/.../tools/context.py` | 服务端注入的 `ToolContext`（shop/actor/role/trace） |
| `src/.../tools/schemas.py` | 严格输入 schema（`extra=forbid`）、商品卡片/详情/比较/库存 DTO、统一信封 |
| `src/.../tools/catalog_tools.py` | `search_products`、`get_product_detail`、`compare_products`、`check_stock` |
| `src/.../tools/registry.py` | 工具白名单注册与调用入口，拒绝未注册工具名 |
| `tests/unit/test_catalog_{schemas,search,compare,stock,tools}.py` | 53 个单元测试 |
| `tests/integration/test_catalog_search_db.py`、`test_catalog_detail_compare_stock.py` | 17 个数据库集成测试 |

### 15.3 硬性要求落实方式

1. 价格与库存只来自 PostgreSQL：所有金额取自 `product_variants.price_cents`，库存取自 `inventory.available_qty`；领域层与工具层没有任何价格/库存常量，RAG 尚未接入。
2. 金额为整数分：`price_cents`/`budget_*_cents` 全链路 `int`，无 float；比较表 `unit=CNY_cents`，展示值由整数分格式化。
3. 不接受任意 SQL：查询全部使用 SQLAlchemy 表达式与绑定参数；`query/brand/category` 中的 `%`、`_`、`\` 会被转义；注入尝试测试断言商品表仍为 30 行。
4. 缺货不冒充有货：无库存记录为 `unknown`（`available_qty=null`），数量为 0 → `out_of_stock`；`in_stock_only` 过滤在 SQL 层完成；`check_stock` 不足时返回真实数量与 `is_available=false`。
5. 比较不生成参数：仅白名单 4 个派生维度 + 29 个商品/SKU 属性；未知键直接 `VALIDATION_ERROR`；缺失值返回 `unknown`，不做推算。
6. 全部查询带 `shop_id`：`search/get_product/list_variants/get_variant/load_compare_sources` 的 WHERE 均包含 `shop_id`；跨店铺集成测试返回空列表或 `PRODUCT_NOT_FOUND/VARIANT_NOT_FOUND`。

### 15.4 验证证据

```text
uv run ruff check .                      -> All checks passed
uv run ruff format --check .             -> 102 files already formatted
uv run pytest tests/unit                 -> 81 passed
uv run pytest tests/integration/test_catalog_search_db.py tests/integration/test_catalog_detail_compare_stock.py
                                         -> 17 passed
uv run pytest -q                         -> 118 passed, 2 third-party warnings, 112.31s
```

集成测试核对的事实：

- 搜索卡片的 `price_cents/currency/available_qty` 与 `product_variants`+`inventory` 聚合逐条相等。
- 预算边界 24900 分包含命中，30000 分以内的结果全部 ≤ 30000。
- `in_stock_only` 结果全部 `available_qty >= 1`；`limit` 上限 20，超量时 `truncated=true`。
- 详情 SKU 数与价格逐条对齐数据库；`stock_summary.available_qty` 等于该商品全部库存之和；`as_of` 等于最新 `inventory.updated_at`。
- 比较表的 `battery_hours/dpi/color` 缺失项为 `unknown`；`price` 与数据库一致；默认维度为 `price/brand/category/stock_status`。
- 库存查询的仓库明细与 `inventory` 行一致；请求量大于可售量时 `is_available=false` 且数量真实。
- 跨店铺搜索为空、详情/库存返回未找到；注入式查询未改变表数据。

### 15.5 已知限制

1. 关键词检索是受控的词法匹配（中文 bigram + `ILIKE`），不是语义检索；同义词和三字以上词组的召回有限，评测将在阶段 13 量化。
2. `ToolSuccess.tool_call_id` 当前按调用生成，尚未落库；`tool_calls` 审计写入属于阶段 9/10。
3. 尚未提供 FastAPI 商品路由与 SSE 商品卡片事件，本阶段只交付工具与 DTO。
4. 搜索按“每个商品一款最低价匹配 SKU”出卡片，同款其他颜色需通过详情或 `check_stock` 查看。
5. 商品无 `image_url` 字段，卡片固定返回 `null`，未伪造图片地址。


## 16. 阶段 7 实施与验证记录（政策 RAG、BGE-M3 双向量与引用）

> 本节记录 2026-10-19 的实测结果。第 14.5 节描述的 384 维哈希 collection 已被阶段 7 取代，
> 仅作为历史记录保留。

### 16.1 边界遵守

- 只实现政策 RAG：embedding、Milvus 双向量集合、hybrid 检索、引用、拒答/转人工、检索评测。
- 未实现意图路由、订单/物流/退货工具、SSE 聊天 API 与前端；未提交 Git。
- 未启动/停止/删除容器，未删除卷；仅对 `shopmate_knowledge_chunks` 执行了被明确授权的重建。
- 未修改参考课程目录。

### 16.2 改动文件

| 文件 | 作用 |
|---|---|
| `src/.../rag/embeddings.py` | 新增 `BgeM3EmbeddingProvider`（单例、惰性加载、dense+sparse 同源）、`EmbeddingMetadata`、L2 归一化与 NaN/Inf 校验；`HashingEmbeddingProvider` 降级为测试夹具并注明不进入生产路径 |
| `src/.../rag/milvus_store.py` | schema v2：`dense_vector`(1024/COSINE) + `sparse_vector`(SPARSE_INVERTED_INDEX/IP) + `embedding_model`；`hybrid_search`/`dense_search`/`sparse_search`/`dense_similarity`；打开时校验结构，不匹配抛 `COLLECTION_SCHEMA_MISMATCH` |
| `src/.../rag/retrieval.py` | `DocumentRetriever`：查询向量 → hybrid top30+top30 → RRF(k=60) → PostgreSQL 权威复核 → 证据打分 → 4-8 片段 → 稳定引用；支路失败诊断与审计 |
| `src/.../rag/citations.py` | 稳定 `citation_id`、引用载荷、4-8 片段选择、版本冲突检测 |
| `src/.../rag/rerank.py` | reranker 协议 + `NoopReranker`；开启但未注册实现时显式报错 |
| `src/.../rag/policy_qa.py` | 政策问答 system prompt（片段为不可信数据）、证据门槛、引用强制校验、拒答/转人工 |
| `src/.../db/repositories/knowledge.py` | 融合后从 PostgreSQL 读取 chunk/document/version 元数据并判定授权 |
| `src/.../rag/ingest/pipeline.py` | 改用 hybrid embedding、写入 `metadata_jsonb.embedding`、NaN/Inf 整批失败并标记可重试 |
| `src/.../core/config.py` | 模型路径/设备/批大小、检索参数、证据阈值、LLM 配置 |
| `scripts/rebuild_knowledge_index.py` | 删旧 collection → 按 1024 维重建 → 全量重导入 → 校验（行数、sparse 覆盖率、维度、范数、指纹） |
| `scripts/eval_retrieval.py` | 5 类问题的检索评测 + dense-only 消融 + 排序差异对比，输出原始 JSON 与摘要 |
| `scripts/smoke_embedding.py` | 无依赖的模型冒烟测试（维度/范数/sparse/相似度） |
| `data/eval/retrieval_cases.jsonl` | 17 条评测用例（normal/no_answer/expired/conflict/cross_shop） |
| `data/eval/conflict/*` | 版本重叠的冲突样本（合成，评测后自动清理） |
| `compose.yaml` / `.env.example` / `.gitignore` / `.dockerignore` | 模型权重挂载与环境变量；权重不入库、不入镜像 |
| `docs/eval-report.md` | 阶段 7 检索评测报告与限制 |
| `tests/**` | 单元与集成测试更新（双向量、hybrid、引用、拒答、冲突、越权、支路失败） |

### 16.3 硬性约束的落实与证据

1. **同源双向量**：`BgeM3EmbeddingProvider._encode` 单次 `model.encode(return_dense=True, return_sparse=True)`；写入与查询走同一实例（进程内单例）。全仓库无 BM25/jieba 稀疏实现，`build_embedding_provider` 只返回 BGE-M3。
2. **dense 1024 + L2 归一化**：`l2_normalise` 在写入与查询两侧执行并断言；冒烟输出 `norm=1.000000`；索引校验 `dense_dimensions=[1024]`、`norms_outside_tolerance=0`。
3. **sparse 稀疏字典**：`{token_id: weight}`（token id 转 int、过滤非正权重），Milvus `SPARSE_FLOAT_VECTOR` + `SPARSE_INVERTED_INDEX` + `IP`；重导入后 `sparse_coverage=1.0`。
4. **hybrid_search**：`AnnSearchRequest` dense top30 + sparse top30，`RRFRanker(k=60)`，融合后再做版本/地区/租户复核。
5. **不静默降级**：`hybrid_search` 失败时用单支路探测归因，返回 `DENSE_BRANCH_FAILED` / `SPARSE_BRANCH_FAILED` / `BOTH_BRANCHES_FAILED` / `HYBRID_SEARCH_FAILED`，并以结构化日志记录 `branch` 与 `degraded=false`；dense-only 仅作为 `dense_only_ablation` 模式存在。
6. **旧向量作废**：384 维 collection 已 drop，按 1024 维重建并全量重导入 21 个版本；`ensure_collection` 对不匹配结构直接报错。
7. **引用**：每条引用包含 `document_id/chunk_id/version_id/title/heading/page_no/version/effective_from/effective_to/snippet`，`citation_id` 由 chunk id 哈希得到，多次检索稳定。
8. **无证据/冲突**：门槛未过返回固定拒答且不返回引用；版本重叠返回转人工；模型出现未标注引用的政策句时整段降级为转人工，草稿不回传。
9. **审计元数据**：`metadata_jsonb.embedding` 覆盖 27/27 子块；检索审计含 `embedding.model/dimension/revision/fingerprint`、双路 limit、RRF k、过滤表达式、被拒原因、耗时。
10. **NaN/Inf 拒绝写入**：编码阶段校验，异常发生在任何 PG/Milvus 写入之前；失败版本记录 `EMBEDDING_NON_FINITE` 等错误码并给出重试命令。

### 16.4 验证证据

```text
uv run ruff check .                        -> All checks passed
uv run pytest -q                           -> 164 passed, 2 skipped (model tests 默认跳过)
SHOPMATE_RUN_MODEL_TESTS=1 uv run pytest tests/integration/test_bge_m3_provider.py
                                           -> 2 passed (61.12s)
uv run python scripts/rebuild_knowledge_index.py --yes
                                           -> 21 个版本 ready；rows=27；sparse_coverage=1.0；
                                              dense_dimensions=[1024]；embedding_models={'bge-m3': 27}
uv run python scripts/ingest.py            -> 21 个版本 ready，0 失败
uv run python scripts/rebuild_knowledge_index.py --verify-only
                                           -> 校验全部通过
uv run python scripts/eval_retrieval.py    -> hybrid accuracy=1.0 / dense_only accuracy=1.0；
                                              ranking 差异 12/17 用例；泄漏 0；误答 0；误拒 0
```

模型信息：`BAAI/bge-m3`，dense 1024，revision `local`，权重指纹 `468b391066f99bc2703682b65930cc82`，
权重位于 `models/bge-m3`（约 2.2 GB，已 gitignore / dockerignore，通过 `EMBEDDING_MODEL_PATH`
挂载，compose 里映射为 `/models/bge-m3:ro`）。

### 16.5 已知问题与风险

1. 双路相对 dense-only 在本数据集上没有可测量提升（见 `docs/eval-report.md` 1.4）；稀疏支路参与了融合（12/17 排序变化）且单独可用，但收益需要更大语料才能量化。
2. 证据门槛 0.62 只在 17 条用例上标定，正负样本边界较窄（0.5836 vs 0.6961），语料变化后需重标定。
3. 冲突检测仅覆盖“同一文档多个同时有效版本”，不覆盖跨文档语义冲突。
4. 未配置 LLM 时政策问答只能返回检索结果或拒答；`PolicyQAService` 会抛 `ANSWER_MODEL_UNAVAILABLE`，不会伪造答案。
5. `DocumentRetriever` 在异步函数内调用同步 Milvus 客户端；MVP 单 worker 可接受，生产应改为线程池或独立检索服务。
6. 检索每轮包含一次 dense 重打分（`dense_similarity`）用于证据门槛，延迟约 300 ms/次（CPU）。

### 16.6 验收整改（D1–D5）与验收结论

上一轮验收给出 CONDITIONAL PASS：2 个阻塞缺陷（D1/D2）、2 个证据缺口（D3/D4）、1 个口径问题（D5）。
2026-10-19 完成整改，边界不变：未进入阶段 8，未新增依赖，未改 `AGENTS.md`/ADR/数据契约，未提交 Git，
未 drop/重建 collection（整改后 `--verify-only` 仍为 rows=27、sparse_coverage=1.0、dense=[1024]）。

| 项 | 状态 | 落实方式与证据 |
|---|---|---|
| D1 证据边界可被闭合标签突破 | 已修 | `build_policy_prompt` 对 snippet 做 `&`/`<`/`>` 转义（存储值不变）；断言 `close_tags=1 system_tags=0 open_tags=1` |
| D2 引用护栏漏判未标注政策句 | 已修（方案 B） | 弃用关键词表 `_CLAIM_HINTS`，改为「陈述句逐句必须有 `[cN]`」，仅放行 `如需/建议/你可以/请联系/如有疑问/以上` 开头或冒号结尾的过渡句；`退货需保持商品完好。` 现判 `uncited_claim` |
| D3 写入侧缺范数断言 | 已修 | `upsert_chunks` 写前 `unit_norm(dense, 1e-3)`，不合格抛 `EMBEDDING_NORM_INVALID` 且整批不落库；只拒绝、不重做归一化 |
| D4 缺对抗性注入测试 | 已修 | 新增 `tests/unit/test_policy_qa_injection.py`（注入 4、承诺护栏 5、逐句引用回归 2）；承诺规则只匹配「已退款 / 退款已批准 / 已赔付 / 免单 / 优惠券已发放」等完成或已批准语式，并带否定前缀豁免 |
| D5 双路消融未证明「有效」 | 已执行、结论如实，口径已确认 | 数据集 17→32 条（原 17 条未改动，新增 `exact_ref`/`near_dup`/`paraphrase` 各 5 条）；复测 hybrid 与 dense-only 指标逐项相同（accuracy 0.9688 / hit 0.8438 / MRR 0.8438 / 片段召回 1.0 / leak 3 / 误答 0 / 误拒 1），排序差异 25/32 |

D5 验收口径（2026-10-19 由项目所有者确认）：消融对照**已执行**，原始结果可复现，结论如实记录为
「在本数据集上未证明双路提升」；双路检索是 `AGENTS.md` §10.4 的硬性契约要求，不因本数据集测不出
收益而取消。据此判定阶段 7 该项通过，且**不对外宣称任何提升百分比**。语料扩充、阈值重标定与
「提升量化」转入阶段 13 的评测工作。

整改后验证：

```text
uv run ruff check .                        -> All checks passed
uv run ruff format --check .               -> 118 files already formatted
uv run pytest tests/unit -q                -> 134 passed
uv run pytest tests/integration/test_milvus_store.py tests/integration/test_retrieval_pipeline.py -q
                                           -> 9 passed + 2 passed
SHOPMATE_RUN_MODEL_TESTS=1 uv run pytest tests/integration/test_bge_m3_provider.py -q
                                           -> 2 passed
uv run pytest -q                           -> 176 passed, 2 skipped（仅因未设 SHOPMATE_RUN_MODEL_TESTS=1）
uv run python scripts/eval_retrieval.py    -> 32 条；两模式指标相同；25/32 排序差异
                                              data/eval/results/retrieval-20261019T042448Z.json
uv run python scripts/rebuild_knowledge_index.py --verify-only
                                           -> rows=27、sparse_coverage=1.0、dense=[1024]、指纹一致
```

## 17. 阶段 8 实施与验证记录（意图路由、查询改写、FAQ 缓存与安全护栏）

> 本节记录 2026-10-19 的阶段 8 实施结果。检索链路完全复用阶段 7 的 `DocumentRetriever`
> 与进程级 BGE-M3 单例，未引入第二套 embedding 或 BM25 实现。

### 17.1 边界遵守

- 未实现订单 / 退货写操作：`ALLOWED_TOOLS` 中不存在 `create_return_request`，
  `return_request` 意图只授予 `check_return_eligibility`（只读资格判断）；测试
  `test_no_route_exposes_a_write_tool` 与 `test_return_request_requires_an_eligibility_check_first`
  对全部 10 类意图逐一断言。
- 未做前端、未新增依赖（Redis 客户端沿用阶段 4 已声明的 `redis`）、未改
  `AGENTS.md`/ADR/数据契约、未提交 Git。
- 护栏为**确定性规则**（正则 + 码表），不依赖模型判断，因此可在无 LLM 环境下断言。

### 17.2 新增与改动文件

| 文件 | 说明 |
|---|---|
| `src/shopmate_ecommerce_assistant/agents/router.py` | 10 类意图路由、加权规则表、置信度与澄清/转人工分流 |
| `src/shopmate_ecommerce_assistant/agents/__init__.py` | 路由公共符号导出 |
| `src/shopmate_ecommerce_assistant/rag/query_rewrite.py` | 实体提取、历史感知改写、关键词扩展、子查询拆分 |
| `src/shopmate_ecommerce_assistant/rag/faq.py` | FAQ 索引与高置信匹配、Redis 缓存、按知识版本失效 |
| `src/shopmate_ecommerce_assistant/safety/pii.py` | PII 识别与掩码（finding 不保留原文） |
| `src/shopmate_ecommerce_assistant/safety/risk.py` | 风险规则表、等级、`primary_reason_code`、handoff 判定 |
| `src/shopmate_ecommerce_assistant/safety/input_guard.py` | 输入护栏：超长 / 注入 / 恶意文档 / 越权 / 高风险 |
| `src/shopmate_ecommerce_assistant/safety/output_guard.py` | 输出护栏：PII / prompt 泄露 / 无引用断言 / 资金承诺 / 未验证实时事实 |
| `src/shopmate_ecommerce_assistant/core/config.py` | 新增 `intent_min_confidence`、`max_user_input_chars`、`query_rewrite_max_*`、`faq_cache_*` |
| `src/shopmate_ecommerce_assistant/rag/policy_qa.py` | `answer()` 接受 `query_plan`，用改写后的 `primary_query` 走同一检索器 |
| `src/shopmate_ecommerce_assistant/db/repositories/knowledge.py` | `version_digest_from_rows` / `load_knowledge_version_digest`（知识版本指纹） |

### 17.3 意图路由表

`ALLOWED_TOOLS` 的工具名与 `docs/05-tool-contract.md` 一致；任何意图都不含写工具。
下表按 `agents/router.py` 的实际枚举值抄录（`PATH_BY_INTENT` / `ALLOWED_TOOLS`），不写概括描述。

| 意图 | 路径（`RoutePath`） | 允许工具 | 缓存资格 |
|---|---|---|---|
| `product_discovery` | `A_structured` | `search_products` | 否 |
| `product_compare` | `A_structured` | `compare_products` | 否 |
| `product_fact` | `A_structured` | `get_product_detail`、`check_stock`、`get_promotion` | 否（价格/库存实时） |
| `policy_faq` | `B_knowledge` | —（检索由 `PolicyQAService` 执行，不走工具） | **是**（唯一可缓存意图） |
| `order_status` | `A_structured` | `get_order_status` | 否（实时） |
| `shipment` | `A_structured` | `get_order_status`、`get_shipment` | 否（实时） |
| `return_eligibility` | `C_deterministic` | `check_return_eligibility` | 否 |
| `return_request` | `C_deterministic` | `check_return_eligibility`（**无写工具**） | 否 |
| `complaint_handoff` | `C_deterministic` | — | 否 |
| `smalltalk_or_unknown` | `safe_fallback` | — | 否 |

工具注册状态（口径校正）：`tools/registry.py` 当前只注册 `search_products`、
`get_product_detail`、`compare_products`、`check_stock`；`get_promotion`、`get_order_status`、
`get_shipment`、`check_return_eligibility` 属阶段 9 实现。因此上表的工具名是“路由授权名”，
不等于“现已可执行”。阶段 9 落地时必须补一条 `ALLOWED_TOOLS ⊆ 注册表` 的一致性测试，
避免路由授权了不存在的工具。

分流规则：`confidence < intent_min_confidence(0.70)` → `SAFE_FALLBACK` + 零工具 + 固定澄清话术；
命中 `OVERRIDE_CODES`（法务、人身安全、隐私/账号被接管、明确投诉）→ 强制 `complaint_handoff`；
`handoff_required = (risk.level >= high) or intent is complaint_handoff`
（后者由 G3 补齐：意图判为投诉时必然升级，不再出现"判投诉但不转人工、且无任何工具"的组合）；
`primary_reason_code` 取最高等级中契约表最早出现者。

### 17.4 查询改写

- 保留实体：订单号（`DEMO|ORD|SO|SHP` + 数字，另识别“订单号：xxx”上下文）、商品 ID（UUID）、
  SKU、金额（元→分，支持 `1,299` / `1，299` 千分位写法）、日期（绝对与相对）、地区（CN/HK/SG…）；
  `entities_before`/`entities_after` 写入审计，丢失则由 `entity_repair` 回填。
- 跳过改写：短而完整的查询（`_is_complete_short`）与 `smalltalk_or_unknown`；去掉指代后
  已完整的问题也不再做关键词扩展。
- 策略可组合但显式记录：`none`、`history_topic`、`pronoun_stripped`、`entity_carryover`、
  `strip_filler`、`keyword_expansion`（上限 `query_rewrite_max_keywords=6`）、
  `subquery_split`（上限 3）、`entity_repair`。
- **单一编码器保证**：`query_rewrite` 模块不导入 embedding / Milvus / BM25（AST 断言
  `test_rewrite_module_never_embeds_or_uses_bm25`）；改写结果由 `PolicyQAService.answer(query_plan=...)`
  交给同一个 `DocumentRetriever`，`test_rewritten_query_uses_the_same_hybrid_retriever_and_provider`
  断言 `provider.query_calls == 1`、`hybrid_search` 被调用且 sparse 非空，即 dense+sparse 仍由
  同一 BGE-M3 单次前向产出、走同一 RRF 融合。

### 17.5 FAQ 缓存

- 匹配：先规范化（NFKC、去填充词、去标点、截断 200），再精确 → 区域不匹配识别 → bigram Dice
  模糊；阈值 `faq_min_match_confidence=0.86`。原因码 `exact/fuzzy/region_mismatch/below_threshold/no_candidate/empty`。
- 缓存键：`shopmate:faq:v1:{shop}:{region}:{locale}:{kb}:{knowledge_version}:{question_hash}`，
  六个要素齐全（问题、店铺、地区、语言、知识库、知识版本），覆盖契约要求的最小五元组。
- 版本失效双保险：`knowledge_version` 由 `load_knowledge_version_digest` 计算（文档
  `current_version/status/生效窗口/parse_status/updated_at` + chunk `max(updated_at)` + enabled
  chunk 数量，sha256 前 16 位）；读取时再校验 `answer.knowledge_version == scope.knowledge_version`，
  不一致即删除并回源。
- 不缓存：非 `policy_faq` 意图、非 `low` 风险、无证据、命中注入标记、无引用、版本不符。
  实时价格 / 库存 / 订单 / 物流因意图不可缓存而天然排除。
- 缓存命中后仍跑 `guard_output`；被拒则删除缓存并返回 `guard_rejected`，避免"缓存绕过护栏"。
- TTL 默认 3600 s（`faq_cache_ttl_seconds`，60 s–7 d）；Redis 不可用时降级为 miss（不报错）。

### 17.6 安全护栏

- 输入：空 → 超长（`max_user_input_chars=2000`）→ 控制字符 → 注入（6 类码：
  `ignore_instructions`、`prompt_exfiltration`、`secret_exfiltration`、`role_override`、
  `command_execution`、`fake_system_tag`）→ 恶意文档指令
  → 越权（他人数据、管理员权限、数据篡改、身份注入）→ 高风险转人工 → 放行（PII 已掩码）。
  输出含 `must_not_call_tools` / `allow_model`，被拦时不进模型、不调工具。
- 输出：系统 prompt 泄露、PII（脱敏）、资金/赔付承诺、无引用政策断言、未验证实时事实、
  HTML/外链清理。`structured_facts_verified` 默认 `False`（fail-closed），结构化工具未回填时
  实时事实声明直接被阻断；无引用断言阻断时追加 `INSUFFICIENT_EVIDENCE_RIGHTS` 风险码。
- 拒答文案固定（超长、注入、越权、转人工、prompt 泄露、资金承诺、无引用、未验证事实），
  保证用户侧口径稳定且不泄露内部规则。

### 17.7 测试矩阵

10 类意图每类 ≥3 条，安全用例独立成目录：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/unit/test_intent_router.py` | 56 | 10 意图参数化（34 条）、风险优先、高额退货 handoff（含 `6,000`/`12,000`/`5,000` 千分位与 `4,999` 下探边界）、低置信澄清、历史指代、政策缓存资格、不暴露写工具、投诉必经 handoff、么/嘛口语问句 |
| `tests/unit/test_query_rewrite.py` | 22 | 实体提取/保留（含商品 UUID 长问句、`1,299` 千分位金额）、短查询不改写、指代补全、代词剥离、订单号/日期/地区/SKU/金额存活、关键词与子查询上限、无第二编码器 |
| `tests/unit/test_faq_cache.py` | 31 | 规范化、精确/模糊/阈值/区域、key 五要素、TTL、版本变更、stale/corrupt 删除、8 种不可缓存原因（含 `route_not_cacheable`）、注入标记、Redis 降级、按店失效、命中后护栏 |
| `tests/unit/test_knowledge_version.py` | 5 | 指纹稳定性、版本/状态/窗口/chunk 变化、顺序无关 |
| `tests/unit/test_pii.py`（G1 新增） | 21 | 地址 4 种写法、掩码不含门牌/栋室、幂等、手机/身份证/银行卡/邮箱/座机回归、订单号/SKU/金额/政策文本不误判、finding 不存原文 |
| `tests/security/test_input_guard.py` | 34 | 超长、空、控制字符、6 类注入、3 类文档/伪标签、4 类越权、4 类高风险、正常放行、PII 掩码、G2 的 8 条语序对抗 + 4 条必须放行反例 |
| `tests/security/test_output_guard.py` | 17 | 引用通过/缺失/未知、拒答放行、已退款与未来承诺阻断、否定豁免、PII、prompt、实时事实 fail-closed/已验证、HTML 清理、4 类其他承诺 |
| `tests/security/test_risk_handoff.py` | 20 | 6 条文本规则、法务压投诉、50 万分边界、低置信分流、7 个服务信号、异常订单、政策描述不误判、JSON payload |

### 17.8 验证证据

```text
uv run ruff check .                        -> All checks passed
uv run ruff format --check .               -> 135 files already formatted
uv run pytest tests/unit/test_intent_router.py tests/unit/test_query_rewrite.py \
  tests/unit/test_faq_cache.py tests/unit/test_knowledge_version.py tests/security \
  tests/unit/test_policy_qa_injection.py -q
                                           -> 196 passed, 1 warning（7.84 s）
uv run pytest tests/unit/test_intent_router.py tests/unit/test_query_rewrite.py \
  tests/unit/test_faq_cache.py tests/unit/test_knowledge_version.py tests/security \
  tests/unit/test_policy_qa_injection.py tests/unit/test_pii.py -q
                                           -> 217 passed, 1 warning（8.00 s）
uv run pytest tests/unit tests/security -q -> 340 passed, 2 warnings（15.98 s）
uv run pytest -q                           -> 372 passed, 2 skipped
                                              （阶段 8 首轮记录；F1 新增 10 条用例后应为 382，
                                               本轮未复跑全量：集成用例依赖容器与真实模型）
```

F1 同一输入的修复前后对照（`route_intent`，默认 Settings）：

```text
"我要退货，这单商品 6,000 元"
  修复前 -> amounts_cents=(0,)       risk_codes=()                  handoff=False
  修复后 -> amounts_cents=(600000,)  risk_codes=(HIGH_VALUE_ORDER,) handoff=True
"我要退货，这单 12,000 元"
  修复前 -> amounts_cents=(0,)       handoff=False
  修复后 -> amounts_cents=(1200000,) risk_codes=(HIGH_VALUE_ORDER,) handoff=True
"这单 4,999 元要退货"
  修复后 -> amounts_cents=(499900,)  risk_codes=()                  handoff=False（50 万分阈值仍生效）
```

### 17.9 已知限制

1. 意图路由基于加权正则，不是分类模型；口语化或跨意图长句依赖 `OVERRIDE_CODES` 兜底，
   边界句子可能落到澄清分支（设计上宁可澄清也不误调工具）。
2. FAQ 模糊匹配用 bigram Dice，无语义相似度；同义改写但字面差异大的问题会 miss（按设计
   走回源检索，不影响正确性）。
3. Redis 集成测试使用内存假实现（`MemoryBackend`），真实 Redis 的 `scan_iter` 失效路径未在 CI 覆盖。
4. 输出护栏的"未验证实时事实"依赖调用方传入 `structured_facts_verified`；默认为 `False`
   属保守策略，接入阶段 9 编排后需由工具执行结果显式置位。
5. 改写只保留 `primary_query` 走检索，`subqueries` 目前仅记录于审计、未做多路召回；
   多子查询融合留待阶段 13 评测决定。
6. 地址掩码在无省市前缀的写法下从「区/县/镇」起匹配，`浦东新` 三字会保留在掩码之外；
   门牌号之后的楼盘名（如 `SOHO 现代城`）不纳入掩码范围。两者都不包含门牌号、栋、室，
   不构成可定位信息。
7. 注入拦截的 `reasons` 现在会同时列出 privilege 类命中码（G2 修复的副产品），
   码表比此前更长；动作仍为 `BLOCK`，规则未被放宽。
8. 低置信度 policy 用例需要 `intent_min_confidence=0.80` 才能构造（默认 0.70 下任何 policy
   规则至少得分 0.71），因此该用例显式注入 Settings，不依赖默认阈值。
9. `FaqService.remember()` 目前没有 src 调用方，聊天链路要到阶段 10 才接入；
   接口已改为 fail-closed，但集成点尚未接线。
10. 金额解析只识别阿拉伯数字（允许千分位 `1,299` / `1，299`）。中文数字金额（“六千元”
    “一万二”）不解析，这类输入不会命中 `HIGH_VALUE_ORDER`；阶段 10 接入订单工具后，
    高额判断应以订单结构化金额（`line_total_cents`）为准，不依赖用户文本。

### 17.10 阶段 8 验收缺陷修复（G1–G8）

首轮自测通过后做验收复验，发现 4 个 P1 缺陷和 4 个测试/注释缺口，全部在阶段 8 边界内修复。
**没有**放宽任何规则、删除用例、降低阈值，也没有改写既有断言。

| 编号 | 缺陷 | 修复方式 | 新增测试 |
|---|---|---|---|
| G1 | 地址 PII 漏检：`张江路 100 号`（门牌前有空格）、无省市前缀的 `浦东新区张江路100号`、`…100号3栋501室` 掩码后残留栋室 | `safety/pii.py` 抽出 `_HOUSE_NUMBER`（`\s*\d+\s*号` + 栋/幢/单元/室最多 3 段）与 `_STREET_TAIL`，新增「区/县/镇/乡/街道」开头的备用模式；最长匹配、不重叠、不存原文的性质保持不变 | `test_shipping_address_is_detected_and_masked`（4 参数）、`test_address_mask_does_not_leave_the_room_visible`、`test_masking_is_idempotent_for_addresses`、`test_order_numbers_skus_amounts_and_policy_text_are_not_pii` |
| G2 | 输入护栏语序被绕过：8 条对抗输入中 5 条被放行 | `safety/input_guard.py` 只补语序分支——`ignore_instructions` 允许「的 + 所有/全部/原有/其他」；`prompt_exfiltration` 加「把…发给我」与「（系统提示词）是什么」；`role_override` 加「从现在起你是…」；`data_tampering` 允许省略主语的「把库存/价格/金额 改成 X」（要求后接具体值）；`other_user_data` 支持动词后置 | `test_attacks_with_reordered_words_are_blocked`（8 参数）、`test_normal_shopping_questions_are_still_allowed`（4 参数）、`test_asking_what_a_price_should_be_is_not_tampering` |
| G3 | `complaint_handoff` 却 `handoff_required=False` 且 `allowed_tools=()`，既不升级也办不了事 | `agents/router.py` 改为 `handoff_required = risk.handoff_required or intent is COMPLAINT_HANDOFF`；`cache_eligible` 逻辑未动，仍为 `False` | `test_complaint_route_is_always_flagged_for_handoff`（2 参数）、`test_normal_policy_route_keeps_handoff_false_and_stays_cacheable`、`test_referential_follow_up_never_yields_a_handoff_free_complaint_route` |
| G4 | `FaqService.remember()` 对 intent/risk/evidence 有 fail-open 默认值，且不接收路由的缓存资格 | `rag/faq.py` 三个判据改必填关键字参数，新增必填 `route_cache_eligible`，为 `False` 时在写 key 前返回 `CacheWrite(False, key, "route_not_cacheable")` | `test_route_ineligible_write_is_rejected`、`test_cacheability_inputs_have_no_defaults`、`test_low_confidence_policy_question_is_not_cached`、`test_policy_question_with_an_order_number_is_not_cached` |
| G5 | 商品 UUID 保留与改写上限缺测试 | 仅补测试，不改实现 | `test_product_uuid_survives_a_long_policy_question`、`test_expansion_bounds_hold_for_a_multi_clause_question`、`test_low_confidence_policy_route_is_not_cache_eligible` |
| G6 | 「那能退么 / 能退嘛」漏召回，落到 `smalltalk_or_unknown` 澄清分支 | `router.py` 的 `policy.how` 与 `eligibility.can` 补 么/嘛 变体（`eligibility` 权重 4 > `policy` 2，故落到 `return_eligibility`） | `test_colloquial_return_question_is_not_smalltalk`（3 参数） |
| G7 | 子查询只入审计、未做多路召回，但 docstring 未说明 | `rag/query_rewrite.py` 仅改 docstring，明确「subqueries 不参与召回」，未偷偷加多路融合 | 无（注释改动） |
| G8 | router docstring 写「history never changes intent」，与零分词句实际行为不符 | 改为「history only resolves a referential follow-up and may only escalate, never downgrade」 | 无（注释改动） |

修复期间的边界遵守：

- 未进入阶段 9，未实现订单/物流/退货/转人工的任何写操作。
- 未新增第三方依赖（`pyproject.toml`、`uv.lock` 未改动）。
- 未改 `AGENTS.md`、`docs/05-tool-contract.md`、`docs/07-security.md`、ADR、数据库模型与迁移。
- 未执行 `git commit` / `git push` / `git reset`；仓库仍无 commit。
- 写操作（`create_return_request`、`create_handoff_ticket`）依旧不在任何意图的 `ALLOWED_TOOLS` 中。

### 17.11 阶段 8 验收复验整改（F1–F2）

用户验收复验提出 1 个 P1（风控漏判）与 1 个证据口径问题，均在阶段 8 边界内修复。

| 编号 | 问题 | 修复方式 | 证据 |
|---|---|---|---|
| F1 | 千分位金额被拆成更小金额：`6,000 元` 只匹配到 `000 元` → `amounts_cents=(0,)`，`HIGH_VALUE_ORDER` 不触发，`handoff=False`；`1,299 元` 被拆成 `29900` + `100` | `rag/query_rewrite.py`：新增 `_NUMBER = (?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d{1,2})?`，供 `AMOUNT_PATTERN`/`BUDGET_PATTERN` 复用；`_to_cents` 先去掉 `,`/`，` 再转 `Decimal`。未放宽“必须带 `元/块/预算` 上下文”的约束，也未改阈值 | 新增 10 条用例：`test_grouped_amounts_parse_as_one_value`（5 参数）、`test_grouped_amount_survives_keyword_expansion`、`test_grouped_high_value_amount_still_requires_handoff`（3 参数）、`test_grouped_amount_below_the_threshold_does_not_hand_off`；前后对照见 17.8 |
| F2 | 本节口径与代码/实测不一致：§17.3 把 `product_compare` 的工具写成 `get_product_detail`（应为 `compare_products`）、`product_fact` 漏写 `check_stock` 与 `get_promotion`、路径列用“结构化 + 检索 / 规则 + 升级”等概括词而非 `RoutePath` 枚举；§17.1、§17.4 引用了不存在的测试函数名；§17.7 写“10 意图参数化（35 条）”实为 34；§17.6 把 6 类注入码写成“5 类”；§17.8 的用例数是 F1 新增用例前的旧值 | 全部改为按 `agents/router.py` 枚举值、`tools/registry.py` 注册表与 `pytest --collect-only` 实测值抄录；补“路由授权名 ≠ 现已可执行”的说明；§17.8 换成本轮实测命令输出 | 用例数以 `uv run pytest <file> --collect-only -q` 实测（router 56、rewrite 22、faq 31、knowledge 5、pii 21、input 34、output 17、risk 20）；命令输出见 17.8 |

修复期间的边界遵守：

- 只改 `rag/query_rewrite.py`、两个阶段 8 测试文件与本节文档；未动 `router.py`、`faq.py`、
  护栏、`AGENTS.md`、工具契约、安全文档、数据库模型或迁移。
- 未实现订单 / 物流 / 退货 / 转人工工具，未做前端，未新增依赖。
- 未执行 `git add` / `git commit` / `git push`；仓库仍无 commit。
- 未跑集成 / E2E：避免在验收阶段写入演示库（容器虽健康，但集成用例会写 PostgreSQL/Milvus）。
- 遗留：`get_promotion`、`get_order_status`、`get_shipment`、`check_return_eligibility` 仍未注册，
  属阶段 9；阶段 9 必须补 `ALLOWED_TOOLS ⊆ 注册表` 的一致性测试。


---

## 18. 阶段 9 实施与验证记录（订单、物流、退货资格/申请与转人工工具）

> 本节记录 2026-10-19 的阶段 9 实施结果。范围严格限定为 5 个工具及其数据、规则、
> 幂等与审计；未做前端、未做最终聊天 API、未提交 Git。

### 18.1 交付物

| 能力 | 实现位置 |
|---|---|
| `get_order_status` / `get_shipment` | `tools/order_tools.py`（归属校验：`shop_id + user_id`，缺失/越权统一 `ORDER_NOT_FOUND`） |
| `check_return_eligibility` | `tools/return_tools.py` + `domain/returns/rules.py`（`demo-return-v1` 纯函数规则） |
| `create_return_request` | `tools/return_tools.py`（只写 `submitted`；HMAC 资格令牌 + 服务端确认 + 幂等） |
| `create_handoff_ticket` | `tools/handoff_tools.py`（只写 `open`；风险等级不可被模型降级） |
| 资格令牌 | `domain/returns/tokens.py`（`v1.<payload>.<hmac>`，绑定店铺/用户/订单项/原因/规则版本） |
| 幂等 | `domain/idempotency.py` + `db/repositories/idempotency.py`（`uq_idempotency_scope` + 请求哈希 + 陈旧接管） |
| 工具审计 | `tools/runtime.py` + `tools/audit.py` + `db/repositories/audit.py`（脱敏输入、最小结果摘要、耗时、幂等键） |
| 数据模型 | `db/models/support.py`（`conversations/tool_calls/idempotency_records/return_requests/handoff_tickets/audit_events`） |
| 迁移 | `alembic/versions/20261019_0003_stage9_order_return_handoff.py` |

### 18.2 安全属性（结构性，非提示词级）

- 身份字段（`shop_id/user_id/risk_level/confirmation_state`）不在任何工具输入 schema 中
  （`extra="forbid"`，`test_tool_registry.py::test_identity_is_not_in_any_input_schema` 验证）。
- `create_return_request` 只有在「令牌验证通过 + 服务端确认授权覆盖该订单项/原因 + 写路径内重查规则仍 eligible」三者同时成立时才写库；输出 `refund_status=not_created` 且文案明确「尚未退款」。
- 退款/赔付/优惠没有任何写工具、没有 `refund_cases` 写路径；LLM 无法承诺资金。
- 相同幂等键重放返回同一资源、同一 `tool_call_id`、`idempotent_replay=true`，不新增 `tool_calls` 行。
- 越权读：缺失订单与他人订单返回同一 `ORDER_NOT_FOUND`，不泄露存在性（数据库层 + 测试双验证）。

### 18.3 验证证据

| 项 | 命令 | 结果 |
|---|---|---|
| 迁移 | `uv run alembic upgrade head` | `20261019_0003 (head)`，6 张新表已在 PostgreSQL 确认 |
| 单元/安全 | `uv run pytest tests/unit tests/security -q` | **434 passed** |
| 集成（本阶段） | `uv run pytest tests/integration/test_order_return_handoff_db.py -q` | **5 passed** |
| 集成（回归） | `tests/integration/test_seed_data.py` + catalog 系列 | 通过（种子/订单唯一性断言恢复为 100） |
| 静态检查 | `uv run ruff check src tests` | 通过（0 error） |

说明：`tests/integration/test_catalog_search_db.py::test_in_stock_filter_never_returns_zero_stock`
在整套集成串跑时偶发 `OSError: Invalid argument`（知识文档 docx 被并发读取），单独运行通过，
为阶段 5 遗留的测试隔离问题，与阶段 9 无关。

### 18.4 设计取舍

- 规则引擎纯函数化（`now` 注入），截止时间恒为 `order_items.delivered_at + 7 天`，
  边界测试覆盖「截止前 1 秒 / 截止 / 后 1 秒」与 499999/500000/500001 分。
- 读时间线只回放订单/物流真实时间戳（placed/delivered/cancelled 与 shipment_events），
  不伪造中间状态节点。
- 幂等「claim 立即提交 + 写库单独事务」，崩溃后 120 秒陈旧接管，避免死锁又防重复。
- `tool_calls` 审计由统一运行时写入；幂等重放跳过审计行、另写一条 `*_idempotent_replay` 审计事件。
- 仓储边界把数据库枚举值归一化为 `StrEnum`（`Enum(str(value))`），使规则比较与种子数据的字符串状态一致。

### 18.5 已知问题与风险

- `get_promotion` 仍是唯一未注册的课程阶段 6 工具；`ALLOWED_TOOLS ⊆ 注册表` 一致性测试
  显式豁免 `get_promotion` 并注明 pending（阶段 10 决定是否补齐）。
- `tool_calls` 审计写入失败仅告警不阻断读结果（写结果已由写库事务内的审计行保证）。
- 客服/管理员读取消费者订单目前仅通过 `support:conversation:read` 权限 + `effective_user_id`
  由服务端注入实现；实际 API/工作台在阶段 10 接线。

### 18.6 下一阶段

阶段 10（未开始）：聊天 dispatcher 接线（把 reader/store/writer 注入 5 个工具）、
`create_return_request` 的确认授权流转、SSE 商品/引用/工单事件与客服工作台；并决定
`get_promotion` 的实现与 `get_order_status`/`get_shipment` 的前端展示。

### 18.7 验收整改（D1/D2）与验收结论

首轮验收给出 CONDITIONAL PASS：唯一阻塞项 D1（P1），另有 D2（P2）。2026-10-19 完成整改，
边界不变：未进入阶段 10，未做前端/聊天 API，未新增第三方依赖，未改 `AGENTS.md`/ADR/数据契约，
未提交 Git。

| 编号 | 缺陷 | 修复方式 | 新增/调整测试 |
|---|---|---|---|
| D1 | 可重试错误（`CONFIRMATION_REQUIRED` / `ELIGIBILITY_EXPIRED` / `LOW_CONFIDENCE` / `UPSTREAM_UNAVAILABLE` 等）会把幂等键写成终态 `failed`；用户确认后用同一 key 重试仍返回同一错误、`created=0`，违反契约 §8.3 与 §7.1 规则 17 | `core/errors.py` 新增 `RETRYABLE_ERROR_CODES`（与 §4 错误码表「可重试」列一致）；`domain/idempotency.py` 协议新增 `release(scope)`（仅删除仍为 `processing` 的记录）；`db/repositories/idempotency.py` 实现条件 `DELETE ... WHERE status='processing'`；`return_tools.py`/`handoff_tools.py` 的 `_create` 改为：可重试 `ToolError` → `_release`，不可重试 → `_mark_failed`，任意 `Exception` → `_release`。审计行（`failed`+`error_code`+`latency_ms`）保留，仅幂等键恢复可重试 | `test_retry_with_same_key_after_confirmation_succeeds`、`test_non_retryable_failure_still_blocks_same_key`、`test_handoff_retry_after_transient_writer_failure`；`fakes.py` 补 `FakeIdempotencyStore.release` 与 `FakeHandoffWriter.fail_attempts` |
| D2 | 服务端注入项（`idempotency_key` / `confidence` / `clarification_attempted`）在工具输入 schema 中，模型可伪造，违反 §5.9/§5.10 | `ToolContext` 新增 `route_confidence`/`clarification_attempted`/`idempotency_key`（带默认值，frozen/slots 不变）；从 `CheckReturnEligibilityInput` 移除 `confidence`/`clarification_attempted`、从两个写工具 schema 移除 `idempotency_key`（`extra=forbid` 拒绝模型传入）；工具改从 context 读；`runtime.py`/`audit.py` 从 context 提取幂等键；`_validate_idempotency_key` 公开为 `validate_idempotency_key` | `test_server_injected_fields_are_not_in_input_schemas`；既有用例的 `idempotency_key` 从 payload 迁到 context |

D2 口径（2026-10-19 由项目所有者确认）：采用「从 schema 移除」（fail-closed）而非「仅覆盖」，
与契约 §5.9「模型不能随意生成」一致。

整改后验证：

```text
uv run ruff check src tests                 -> All checks passed
uv run ruff format --check src tests        -> 125 files already formatted
uv run pytest tests/integration/test_order_return_handoff_db.py -q -> 5 passed
uv run pytest -q                            -> 485 passed, 2 skipped（仅因未设 SHOPMATE_RUN_MODEL_TESTS=1）
```

据此阶段 9 判定为 **验收通过**。

## 19. 阶段 11：Vue 3 前端（实现 + 验收 + 修复）

### 19.1 范围与产出

阶段 11 在 `frontend/` 下交付 Vue 3 + Vite 6 + TypeScript（strict）+ Pinia + Vue Router + Element Plus 前端，
覆盖消费者聊天（会话 CRUD + SSE 流式 + 工具状态 + 引用侧栏）、商品搜索/比较/详情、订单/物流/退货向导、
转人工、客服工作台、知识库管理端、统一 API client（信封解包、稳定错误码、401 静默刷新、幂等键）与双测试层
（Vitest 组件测试 + Playwright E2E）。全程未改动后端业务规则，未提交 Git，未动任何 Docker 容器。

### 19.2 2026-10-19 首次验收：FAIL

typecheck 0 错误、Vitest 117 全过、构建成功，但 Playwright 仅 3/15。三个必修项：

| 编号 | 缺陷 | 根因 |
|---|---|---|
| P0-1 | 登录成功后被路由守卫弹回 `/login?next=/`，所有登录后页面不可用 | `src/api/client.ts` 的模块级 `let accessToken` 非响应式，`stores/auth.ts` 的 `isAuthenticated` computed 首次求值后永久缓存 false |
| P0-2 | 登录失败无错误提示 | `LoginView.vue` catch 中先赋 `error` 再 `await loadCaptcha()`，后者首行清空 error |
| P0-3 | e2e 基建掩盖 P0-1 | 验证码读取竞态；`toHaveURL(/\/(\?.*)?$/)` 被 `/login?next=/` 误匹配（假通过）；过松断言 |

### 19.3 修复内容（2026-10-20）

1. **P0-1**：`client.ts` 改用 `shallowRef` 存 token（单一响应式数据源），`stores/auth.ts` 的 computed 自动生效；
   `auth.test.ts` 新增「先求值 → 登录 → clearSession」响应性回归护栏（117 → 118 用例）。
2. **P0-2**：`LoginView.vue` 的 `onLogin`/`onRegister` catch 改为「先算 error → 刷新验证码 → 回填 error」。
3. **P0-3**：`e2e/helpers.ts` 与 `auth.spec.ts` 先等待验证码题目就绪；收紧登录成功断言为
   `not.toHaveURL(/\/login/)` + `.sm-composer-input` 可见；原则为可收紧、禁止放宽。
4. **P0-4（修复过程中新发现）**：后端登录 cookie 的 `Path=/api/v1/auth` 使页面 JS 读不到 CSRF cookie，
   静默刷新永远不发起请求（实测 reload 后无任何 `/auth/refresh` 请求）→ 刷新页面必回登录页。
   修复在代理层完成、不触碰后端代码：`vite.config.ts` dev 代理重写 `set-cookie` path 为 `/`；
   `web/nginx.conf` 生产侧同步 `proxy_cookie_path /api/v1/auth /;`。
5. **e2e 数据耦合**：上一轮提交的退货会让下一轮资格检查命中 `DUPLICATE_RETURN`；
   `order-return.spec.ts` 的 `beforeAll` 自动执行幂等 fixture 重置演示数据。
6. 补齐 `frontend/README.md` 与 `frontend/e2e/README.md`。

### 19.4 修复后门禁结果（2026-10-20 00:47，全部实测）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 类型检查 | `npm run typecheck`（app）+ `vue-tsc --noEmit -p tsconfig.node.json`（node/e2e） | ✅ 0 错误 |
| 组件测试 | `npx vitest --run` | ✅ 13 文件 / 118 测试通过 |
| 生产构建 | `npm run build` | ✅ 7.2s |
| E2E | `VITE_API_PROXY_TARGET=http://localhost:18001 npx playwright test`（msedge 通道） | ✅ **15/15 通过**（57.6s） |

E2E 覆盖：未登录重定向、错误密码提示、登录落地首页、刷新保持登录、消费者无客服/管理入口、
SSE 流式与停止、会话新建/重命名、商品搜索/比较/详情、物流时间线、退货资格→确认→幂等提交、转人工建单。

### 19.5 已知后端缺口（非前端缺陷，阶段 12 前决策）

- `/api/v1/support/*` 未注册（客服工作台页面呈错误态）。
- admin 的文档上传、`POST /admin/documents/{id}/reindex`、`PATCH`/`DELETE /admin/chunks/{id}` 未注册。
- 登录 cookie `Path=/api/v1/auth` 建议在后端源头改为 `/`（当前由代理层重写兜底）。

### 19.6 结论

阶段 11 四项验收门禁全部通过，可以进入阶段 12（进入与否由项目所有者确认）。

## 20. 阶段 12：测试、安全与故障演练（完成）

### 20.1 范围与产出

只做测试补全、安全验证、故障演练与报告；**未新增业务功能**、未提交 Git、未停止/重建/删除任何容器。

| 产出 | 路径 |
|---|---|
| 测试与安全报告 | `docs/test-report.md`（§16.2 与 SEC-01–19 矩阵、故障演练矩阵、缺口） |
| API 边界安全测试 | `tests/integration/test_api_security.py`（19 例） |
| 故障演练与日志脱敏 | `tests/unit/test_fault_drill.py`（11 例） |
| 跨店铺知识隔离（真实 Milvus+PG） | `tests/integration/test_retrieval_pipeline.py::test_another_shops_knowledge_is_never_retrieved` |
| 前端断线状态机测试 | `frontend/src/composables/useChatStream.test.ts`（6 例） |
| 浏览器断线恢复 E2E | `frontend/e2e/chat.spec.ts::SSE 断线：显示可重试错误，重试后恢复` |
| 种子测试隔离修复 | `tests/integration/test_seed_data.py`（按 `SM-2026-*` 作用域断言，保留强度） |
| 前端断线显示修复 | `frontend/src/views/ChatView.vue`、`frontend/src/components/chat/ChatThread.vue`（仅显示层） |

### 20.2 门禁实测（2026-10-20 01:10）

```text
uv run ruff check .                 -> All checks passed!
uv run ruff format --check .        -> 212 files already formatted
uv run pytest -q                    -> 576 passed, 2 skipped, 26 warnings in 130.57s
npm run typecheck                   -> 0 错误
npx vitest --run                    -> 14 files / 124 tests passed
npx playwright test                 -> 16 passed (51.3s)   # msedge，API 走本机 18001
```

2 条 skip 均为 `test_bge_m3_provider.py`（需 `SHOPMATE_RUN_MODEL_TESTS=1` 与 2.2 GB 权重），
阶段 7 曾实测通过；真实模型质量评测属阶段 13。

### 20.3 本轮修复的 2 个缺陷

1. **测试隔离（非产品缺陷）**：`test_seed_data.py` 断言全表 100 订单，被 Playwright fixture 合法写入的
   `E2E-*` 合成订单打破。改为按种子自身 `order_no` 前缀断言 100 条，同时保留全表唯一性与冒烟地址断言。
2. **产品缺陷 P2（已最小修复）**：SSE 断线时 `ChatView.onSend` 把 `network` 与“用户停止/重复请求”
   合并处理，直接 `resetTurn()` 丢弃错误态；`ChatThread` 在正文为空时不渲染气泡。结果是断线后用户
   只看到消息消失、无任何提示，违反 §16.2.12 与 §13.4。修复为：断线保留 `turn.error`（含“重试”入口），
   气泡渲染条件纳入 `error`/`stopped`。新增 E2E 与 6 条单测锁定该行为。

### 20.4 已知缺口（详见 `docs/test-report.md` §7）

- `/api/v1/support/*` 未注册 → SEC-01（客服端）与 SEC-19（质量标记）无法验证。
- 数据契约无订单级 `refunded` 状态；等价语义由 `order_item.status=returned` **或**
  `return_request.status=completed` 覆盖（后者已于 20.6 补齐阻断逻辑与用例）。
- admin 跨店铺访问缺“第二店铺 admin”运行时用例（知识检索侧已双向验证）。
- Redis 不可用时 API 为 fail-closed 的 500 `INTERNAL_ERROR`（安全但可用性差），建议阶段 14 映射为 503。
- 测试夹具的短 HMAC 密钥触发 `InsecureKeyLengthWarning`；生产需校验 `JWT_SECRET` ≥32 字节。

### 20.5 下一阶段

阶段 13（评测、RAGAS 与压测）**未开始**。建议内容：100+ 条评测用例、baseline 与优化对照、
检索/生成指标、Locust 压测（健康检查/商品搜索/政策问答/订单查询/SSE 并发）。

### 20.6 验收后修复（2026-10-20）

阶段 12 首次验收为 **CONDITIONAL PASS**（15 项必测 14 项证据充分，无高危、无测试削弱）。
本轮只关闭验收清单 4 项，未进入阶段 13、未新增业务功能、未提交 Git、未操作容器。

| 项 | 改动文件 | 结果 |
|---|---|---|
| **A（P2）** 必测项 2「已退款/已退货」口径 | `db/repositories/orders.py`（新增 `_CLOSED_RETURN_STATUSES`/`_BLOCKING_RETURN_STATUSES`，`find_active_return` 把 `completed` 视为阻断记录）、`domain/orders/ports.py`、`tools/return_tools.py`（调用点 `existing`→`blocking_return`）、`docs/05-tool-contract.md` §7.1、`tests/unit/test_return_rules.py`(+5)、`tests/integration/test_order_return_handoff_db.py`(+3) | 已关闭；**含 1 处业务规则变更** |
| **B（P3）** 报告摘要数字 | `docs/test-report.md` §1 | 13/4/2 → **15 通过 / 3 部分 / 1 无法验证**（与 §5 十九行逐行核对一致） |
| **C（P3）** admin 路由覆盖 | `tests/integration/test_api_security.py` | 5 → **8 条**（补 `POST /knowledge-bases`、`GET /documents/{id}`、`POST /eval/run`） |
| **D（P3）** 系统 prompt 不入日志 | `tests/unit/test_fault_drill.py`、`tests/integration/test_api_security.py` | 两个用例各 +3 标记（`你是 ShopMate`/`<evidence`/`NO_EVIDENCE`） |

**A 项的实测事实与业务规则变更**（详见 `docs/test-report.md` §11.1）：

- 改动前实测：`order_status=completed` + `item_status=active` + 窗口内 → `RETURN_ELIGIBLE`；
- 而 `src/` 中没有任何代码把 `order_items.status` 写成 `returned`，故退货申请被审批为 `completed`
  之后仍可再次提交 → 重复退货风险；
- 因此按验收指令做**最小修正**：`find_active_return` 现在同时阻断 `submitted/under_review/approved/completed`，
  `rejected/draft/cancelled` 不阻断（被拒后允许在期限内重新申请）。
  该方法语义变为「查找阻断新申请的退货记录」，读路径（`check_return_eligibility`）与写路径
  （`create_return_request`）都经过它，因此两条路径同时闭环。

**门禁实测（2026-10-20 01:30）**：

```text
uv run ruff check .                 -> All checks passed!
uv run ruff format --check .        -> 213 files already formatted
uv run pytest -q                    -> 587 passed, 2 skipped, 26 warnings in 134.76s
uv run pytest --collect-only -q     -> 589 tests collected
uv run pytest tests/security -q     -> 86 passed
uv run pytest tests/unit/test_return_rules.py tests/integration/test_api_security.py tests/unit/test_fault_drill.py -q
                                    -> 63 passed
docker compose config               -> 通过
npm run typecheck                   -> 0 错误
npx vitest --run                    -> 14 files / 124 tests passed
npx playwright test                 -> 16 passed (51.2s，本机 18001 API，msedge)
```

数量守卫：后端 **576 → 587**（+11，无删除）；vitest **124（不变）**；Playwright **16（不变）**。

**结论：阶段 12 判定 PASS**（1 个 P2 + 3 个 P3 全部关闭，门禁全绿，无高危、无测试削弱）。
阶段 12 遗留缺口（`/api/v1/support/*` 未注册、admin 跨店铺运行时用例、Redis 500 fail-closed、
真实模型 skip）性质与归属不变，分别留给后续阶段或阶段 14，不影响本阶段判定。

---

## 21. 阶段 13：评测、RAGAS 与压测（2026-10-20）

### 21.1 范围与产出

| 类型 | 文件 |
|---|---|
| 数据集 | `data/eval/eval_questions.jsonl`（136 条，sha256 `7606cfce…`）、`data/eval/retrieval_cases.jsonl`（58 条，sha256 `856f3338…`） |
| 权威原始结果 | `data/eval/results/stage13-20261020T013230Z.json`（检索三配置 + 业务 136 条 + 生成代理 + 政策答案 36 条 + 索引快照） |
| 历史原始结果 | `stage13-20261019T181157Z.json`（数据文件已丢失的 136 条版本 records 来源）、`stage13-20261019T184441Z.json`（政策答案跑在 100 条版本上，已取代） |
| 压测 | `locust-stage13-u20_stats.csv` / `locust-stage13-u40_stats.csv` 等 8 个 |
| 脚本 | `scripts/eval_stage13.py`（四部分可单独运行）、`scripts/verify_stage13.py`（独立复算）、`scripts/locustfile.py` |
| 报告 | `docs/eval-report.md` 第 2 章（含 2.14 整改记录） |

### 21.2 首次验收（2026-10-20 09:00）：CONDITIONAL PASS

只读核查（未改文件、未提交 Git），从 `stage13-*.json` 的 records 独立重算。已复算一致的部分不再改动；
四个阻断项：

1. **D1 数据集版本漂移**：报告/原始结果写 136 条 / sha `48cdae75…`，磁盘只有 100 条 / sha `6cc9dc7c…`。
2. **D2 越权分母**：报告写 1.00（6/6），实际 `authorization` 用例 8 条；且 100 条文件里无该标签，
   `_rate()` 分母为 0 会返回 `None`。
3. **D3 延迟标签错**：n=127 = 109 聊天轮 + 18 政策检索轮被并进同一列表，标签却写"非检索轮"。
4. **D4 吞吐与 CSV 不符**：写 22.5→29.4 req/s（+31%），CSV 汇总行是 23.08→29.61（+28.3%）。

### 21.3 整改内容（本轮，不进入阶段 14、不提交 Git）

1. **D1 选方案 A（恢复 136 条）**：从 `stage13-20261019T181157Z.json` 的 `records` 回填 eval-101…136
   （question/intent/tool/behavior/risk/tags 逐条断言与 records 一致），补 `reference_answer`（36 条按期望行为撰写）、
   `locale/region/allowed_citation_document_keys/is_synthetic`、`history`（eval-107…110，**重建值**）、
   以及 eval-095 的 `authorization`+`cross_user` 标签与 `expected_behavior=denied`。
   前 100 条除 eval-095 外逐字节未改。新 sha256 `7606cfceb6ad101ca89e4717169c5841f956b4de273ab26002c81074913f3d51`。
2. **D2**：`scripts/eval_stage13.py` 输出 `authorization_cases` 与 `unauthorized_blocked_cases`，
   分母写进原始结果；本轮 **8/8**。
3. **D3**：每条 record 增加 `latency_kind`（`chat_turn` / `policy_retrieval` / `handoff_decision`），
   汇总拆成 `latency` 与 `policy_retrieval_latency`，且**只从 records 派生**（不再用旁路列表）。
4. **D4**：报告改取 CSV `Aggregated` 行 `Requests/s`：23.08 → 29.61（+28.3%），P95 570 → 2400 ms 不变。
5. **D1 根因修复（超出"只改报告"的必要项）**：`src/.../synthetic/writers.py::write_eval_cases`
   原先**无条件重写** `data/eval/eval_questions.jsonl` 为生成的 100 条，`scripts/seed.py` 与
   4 个集成测试都会调用 `write_source_files()`，因此每次跑 seed/pytest 都会把手写的 36 条删掉
   ——这是 D1 的真正原因，也是"报告 136 / 磁盘 100"反复出现的原因。改为"文件存在且非空则不覆盖"，
   `tests/integration/test_seed_data.py` 两处 `== 100` 改为 `>= 100`（保留 id 唯一性、意图覆盖断言）。
   重跑 pytest 后文件仍为 136 条、sha 不变（见 21.5）。**未改任何业务规则、未删除用例、未改期望值。**
6. **随附**：records 落盘 `first_delta_ms`；原始结果新增只读 `index` 快照
   （PG 48 行 / 32 内容哈希 / 21 ready 版本；Milvus `count(*)` 28 行含 1 孤儿 `b4d04e8f…`，交集 27，
   与 `index-verify.json` 一致）；政策答案在 136 条版本上重跑（28 → **36 条**，与 2.6 同一 sha）。

### 21.4 整改后关键数字（同一次运行，可由 `scripts/verify_stage13.py` 复算）

- 检索 58 条：R@1/3/5/10 = 1.00、MRR = 1.00、ctxP 0.8459、ctxR 1.00、主引用 1.00、chunk 引用精度 0.2664
  （optimised 0.3090、片段 6.22→5.03）、行为正确率 0.9828、误答 0、误拒 1（`exact-05`）。
  hybrid 与 dense-only 仍**无差异**（不得写成"混合检索提升召回"）。
- 业务 136 条：意图 **0.7059**（96/136）、工具 0.6691、任务成功 **0.6324**（86/136）、
  严格拒答 0/7、宽松不编造 4/7、越权拦截 **1.00（8/8）**、转人工 0.8182 / 1.00、泄漏 0、注入 11/11、错误 0。
- 工程：聊天轮 P50 **25.63** / P95 **43.10 ms**（n=109）；政策检索轮 **153.61 / 202.32 ms**（n=18）；
  首 token 24.99 / 42.39 ms（n=107，逐轮落盘）；政策答案（7B）P50 **1373.22** / P95 **2936.89 ms**（n=36）。
- 政策答案 36 条：answered 5 / handoff 4 / refused 27；可答应答率 0.1724（5/29）；无答案拒答 1.00（7/7）；
  引用合规 1.00；faithfulness 0.88（5 条，含 2 条哨兵污染）；relevancy 0.52；token 77,709；本地 0 USD。
- 压测：20u 1350 req / 0 失败（P95 570 ms）；40u 1762 req / 2 失败（P95 2400 ms，P99 3200 ms）；
  吞吐 23.08 → 29.61 req/s。

### 21.5 门禁（本轮实测）

```text
uv run ruff check .          -> All checks passed!
uv run pytest -q             -> 587 passed, 2 skipped, 26 warnings in 141.91s（收集 589，与阶段 12 基线一致）
uv run python scripts/verify_stage13.py -> 全部一致（0 不一致项）
sha256sum / wc -l            -> 磁盘 == 原始结果 datasets == 报告 2.1/2.13
sha256sum（pytest 之后）      -> 7606cfce… 仍为 136 行（seed 不再覆盖数据集，D1 不会复发）
```

未提交 Git；未重启/重建/删除任何容器；未改业务代码（`policy_qa.py` 的 `NO_EVIDENCE` fail-open 仍待授权）。

### 21.6 未做 / 风险

- 官方 `ragas` 包仍未运行（自建 LLM-as-judge 代替），2.5.3 的"未运行"保留。
- 结构化 faithfulness / relevancy 代理未落盘逐轮（需重跑脚本复现），已在报告 2.11 注明。
- 数据集有重建字段（`reference_answer` 36 条、`history` 4 条），已在 2.2 / 2.11 标注；
  `multi_turn` 意图 0.75→1.00 的 +1 来自 `history` 重建，不是系统改动（见 2.6 注）。
- `ruff format --check .` 仍会对 `scripts/locustfile.py` 报"would reformat"（该文件本轮未改，属既有格式差异）。

### 21.7 结论

阶段 13 的四个阻断项全部关闭，数据集/原始结果/报告三方指纹一致，头条指标可由独立脚本复算。
**可判 PASS（待所有者复核）**；按阶段门禁，当时（2026-10-20）未做任何阶段 14 准备性改动，
阶段 14 随后在 §22 完成。

## 22. 阶段 14：生产部署、文档与演示（2026-10-20）

### 22.1 范围与产出

本轮只做部署、文档与演示，**未新增业务功能**，未提交 Git，未重启/重建/删除任何既有容器与数据卷。

新增：

| 文件 | 作用 |
|---|---|
| `compose.prod.yaml` | 生产编排：独立项目名/卷、数据服务不暴露端口、只读根文件系统、cap_drop、资源限制、日志轮转、固定镜像、一次性 `migrate`、`tools` profile（seed/ingest） |
| `web/Dockerfile.prod` | 两段式前端镜像：Node 构建 Vue 产物 → Nginx 非 root 运行 |
| `web/nginx.prod.conf` | 生产反代：SSE 不缓冲、CSP/安全头、`server_tokens off`、认证边缘限流、25 MB 请求体上限 |
| `web/shopmate-proxy.inc` | 两条 API location 共用的反代片段（含 cookie Path 重写） |
| `web/Dockerfile.prod.dockerignore` | 生产前端构建上下文（排除 node_modules/dist/data/models 等） |
| `.env.prod.example` | 生产变量模板，全部为占位符，敏感项强制注入 |
| `scripts/check_deploy_security.py` | 34 项部署安全静态复查（退出码可用于门禁） |
| `scripts/demo_accounts.py` | 幂等设置 3 个合成演示账号口令，并列出其订单 |
| `tests/unit/test_trusted_hosts.py` | Host 头白名单的 4 个用例 |

修改：

| 文件 | 改动 |
|---|---|
| `README.md` | 从空文件补全为完整使用说明（环境、启动、迁移、seed、演示账号、门禁、生产部署、已知限制、故障） |
| `docs/06-api.md` | §12/§13 增加「实现现状」勘误：support 路由与管理端写接口未实现 |
| `docs/07-security.md` | 新增 §18 阶段 14 安全复查（34 项结果、新增控制、剩余风险、复现命令） |
| `docs/demo.md` | 由阶段 2 设计稿升级为 v1.0 可执行脚本（真实账号/订单/政策版本/命令） |
| `docs/README.md`（新增） | 文档索引与阅读顺序 |
| `src/.../core/config.py` | 新增 `trusted_hosts` 配置与 `allowed_hosts` 属性（默认空=不启用） |
| `src/.../main.py` | 当 `TRUSTED_HOSTS` 非空时挂载 `TrustedHostMiddleware` |

### 22.2 生产配置差异（相对 `compose.yaml`）

1. 项目名 `shopmate-prod`，5 个独立 named volume，与开发栈完全隔离。
2. 仅 `web` 暴露 `${WEB_PORT:-8080}`；PG/Redis/etcd/MinIO/Milvus 与 API 均不映射宿主端口。
3. `api`/`web`：`read_only: true` + `tmpfs`、`cap_drop: ALL`、`no-new-privileges`、CPU/内存上限。
4. 全部常驻服务 json-file 日志轮转（10 MB × 3）。
5. 迁移拆成一次性 `migrate`（API 依赖其成功），API 命令为 `uvicorn --no-access-log --workers 1 --proxy-headers`，无 reload。
6. 镜像来自 `${API_IMAGE}`/`${WEB_IMAGE}`（缺失即启动失败，禁止 latest）。
7. 前端生产镜像从 `frontend/` 源码构建，不再使用 `web/public` 占位页。

### 22.3 执行的命令与结果

```text
uv run ruff check .                                  -> All checks passed!
uv run pytest -q                                     -> 591 passed, 2 skipped（阶段 13 基线 587，+4 为 Host 白名单用例）
docker compose -f compose.prod.yaml --env-file .env.prod.example config --quiet -> 退出码 0
uv run python scripts/check_deploy_security.py       -> 34 项 PASS / 0 WARN / 0 FAIL
docker build -f web/Dockerfile.prod -t shopmate-web:0.1.0-prod . -> 成功（Node 构建 + Nginx 运行段）
（前端）npm run build                                 -> ✓ built in 13.92s
uv run python scripts/demo_accounts.py               -> 3 个账号 password-set；复跑全部 unchanged（幂等）
uv run python scripts/verify_stage13.py              -> 全部一致（0 不一致项），数据集 sha 7606cfce… / 136 条
curl http://localhost:18000/health                   -> {"status":"ok"}
curl http://localhost:18000/ready                    -> {"status":"ready","checks":{postgres/redis/milvus: ok}}
```

生产 web 镜像运行验证（临时容器，验证后删除）：

```text
docker run -d --name shopmate-web-prod-check --network shopmate_default --read-only \
  --tmpfs /tmp --tmpfs /var/cache/nginx --cap-drop ALL --security-opt no-new-privileges:true \
  shopmate-web:0.1.0-prod
-> Status: Up (healthy)
-> /healthz: ok
-> / : <title>ShopMate 电商智能客服</title>
-> id: uid=101(nginx) gid=101(nginx)
-> /api/v1/auth/captcha: nginx access log 记录 404 22 字节 = 上游 FastAPI 的 {"detail":"Not Found"}
   （转发链路成立；404 原因是运行中的开发 API 容器仍是 2026-10-18 的旧镜像，只有 /health、/ready）
```

### 22.4 过程缺陷与修复

| 问题 | 根因 | 修复 |
|---|---|---|
| `compose ... config` 报 `pids_limit` 与 `deploy.resources.limits.pids` 冲突 | Compose v5 对 `pids_limit` 与 `deploy.resources.limits` 同时出现时的归一化冲突 | 移除 7 处 `pids_limit`，保留 CPU/内存上限 |
| 生产 web 容器启动即退出：`"server_tokens" directive is not allowed here` | `server_tokens` 被写在 main 上下文 | 移入 `http {}` 块，重建镜像后 healthy |
| 安全脚本误报「内联口令」 | 正则把 `${POSTGRES_PASSWORD:?set ...}` 里的 `POSTGRES_PASSWORD:` 当成字面量 | 改为解析 YAML 的 `environment`，只判定非插值的敏感值 |

### 22.5 未做 / 风险

- **未在全新主机执行完整 checklist**：本机开发栈（2026-10-18 创建的旧 API 容器、运行中的 5 个数据服务）正在使用中，未启动生产栈，以免占用 8080/数据卷；`docs/09-release-checklist.md` §10 已如实标注“部分通过”。
  > **补注（2026-10-20 阶段 15 验收整改）**：生产栈已在 §22.7 整改时**实跑**（`migrate` exit 0、7 个容器 healthy、`8080` 登录成功），
  > 因此本条“未启动生产栈”只对**本阶段首次执行时**成立；仍然成立的只有“未在**全新主机**复核 checklist”。
  > 本节历史结论不改，仅补此注，避免与 §22.7 的实跑记录冲突。
- **未重建开发 API 容器**：容器内 API 仍是阶段 4 镜像（只有 `/health`、`/ready`），因此全流程烟测 7.1–7.14 未在本轮容器环境执行；这些能力由 591 项测试与阶段 13 评测覆盖，接口层证据见 `docs/test-report.md`。
- 客服工作台 API、管理端上传/重建索引仍未实现（阶段 14 只做文档勘误，不扩范围）。
- 无 `/metrics`、无自动备份任务；均在部署手册 §12 列为已知缺口。
- BGE-M3 权重未纳入仓库与镜像，首次部署需自行准备 `./models/bge-m3`。

### 22.6 结论

阶段 14 的交付物（README、部署手册、发布清单、演示脚本、生产编排、备份/恢复、安全复查）已完成并可复现；
`compose.prod.yaml` 通过校验，生产前端镜像实际构建并在只读 + 非 root + cap_drop 条件下 healthy 运行。
**状态：完成（部分验证项待全新主机复核）**。

阶段 15（简历证据与面试材料）**未开始**。

---

### 22.7 只读验收（2026-10-20 10:20，CONDITIONAL PASS）与整改复评（2026-10-20 10:30–10:55）

#### 22.7.1 首轮验收结论与范围

2026-10-20 10:20 的只读验收判定 **CONDITIONAL PASS**：静态项全部通过，但有 2 个 P1（阻断）
与 4 个 P2。本轮只做整改，不进入阶段 15、不提交 Git、不改业务规则与评测口径。

已复现通过（验收方提供，本轮未重复）：
`check_deploy_security.py` 34 PASS/0 WARN/0 FAIL、两份编排 `config --quiet` 均 exit 0、
`verify_stage13.py` 全部一致、Docker 29.8.0 / Compose v5.5.1、alembic 4 版本单链 head=`20261019_0004`。

本轮**自己复现**的两个 P1（改动前，只读）：

```text
# P1-1：TestClient + Settings(trusted_hosts="shopmate.example.invalid")
http://shopmate.example.invalid  -> 200 {"status":"ok"}
http://127.0.0.1:8000            -> 400 Invalid host header      ← 容器 healthcheck 的 Host
https://attacker.example.invalid -> 400 Invalid host header

# P1-2：开发栈实际返回
curl :3000  -> 当前为阶段 4 脚手架页面。消费者聊天与企业知识库界面将在后续阶段实现。
curl :18000/openapi.json -> ['/health', '/ready']    # 2026-10-18 旧镜像
```

#### 22.7.2 整改内容

| 项 | 改动 | 文件 |
|---|---|---|
| P1-1 | `TRUSTED_HOSTS` 模板改为 `127.0.0.1,localhost,shopmate.example.invalid`；编排默认值 `${TRUSTED_HOSTS:-127.0.0.1,localhost}`；新增 5 条单测（含“仅域名时回环 400”的回归用例） | `.env.prod.example`、`compose.prod.yaml`、`tests/unit/test_trusted_hosts.py` |
| P1-2 | README §4.5 改写为 3 条可用路径（5173 dev / 生产前端镜像 8080 / §8 生产栈）+ 顶部警示；§4.2 补占位页说明；§9 增加限制行；§8 镜像改为 `docker build`；§7 补 `--host`；§8/§11 章号修正 | `README.md`、`docs/09-release-checklist.md`（6.3/6.6） |
| P2-3 | Milvus 备份/恢复改三卷（etcd/minio/milvus），卷名用 `${COMPOSE_PROJECT_NAME}` 推导，恢复序 etcd→minio→milvus→api，并给 3 条恢复后校验 | `docs/08-deployment.md` §6.1/6.4/6.5 |
| P2-4 | 全部 `pg_dump`/`pg_restore`/`psql` 改为 `exec -T … sh -c '… "$POSTGRES_USER" …'`，宿主不再需要导出变量（8 处） | `docs/08` §6.2/6.3/§8、`docs/09` 3.4/3.5/4.2/4.3/5.2.3 |
| P2-5 | 新增 §3.3「演示前重置（每条演示开头执行）」：优先换单（只读 SQL，列 `order_no`）+ 受限清理（demo 库/`is_synthetic`/逐条确认），并显式禁止删卷重置；§3.4 自检加三条断言 | `docs/demo.md` |
| P2-6 | 生产栈实跑（见 22.7.3） | `.env.prod`（本地，gitignored） |
| P3-7 | CI 增加 prod `config --quiet` 与 `check_deploy_security.py --strict` | `.github/workflows/ci.yml` |
| P3-10 | 生产拒绝默认密钥（`Settings.ensure_production_secrets()` + `create_app` 调用 + 4 条单测）；`--forwarded-allow-ips` 收敛为内网/容器网段；生产编排移除全部 `build:` 段 | `core/config.py`、`main.py`、`tests/unit/test_production_secrets.py`、`compose.prod.yaml`、`.env.prod.example`、`docs/07` §18.6、`docs/08` §2/§3.1/§10 |

文档同步：`docs/07-security.md` 新增 §18.6（整改表 + 证据 + 仍存风险）、`docs/08` §2/§3.1/§4.1/§4.6/§6/§7.2/§10、
`docs/09` §5.1 注记（Git Bash 路径、空库登录 500 的成因）与 §10 实测记录。

#### 22.7.3 生产栈实跑（P2-6，已获授权）

命令与数据影响在 10:30 的确认中被逐条列出并获「确认执行」。实测：

```text
docker build -t shopmate-api:0.1.0 .                                  -> 成功（7m14s，python:3.12-slim 两段式）
docker compose -f compose.prod.yaml --env-file .env.prod up -d <5 服务>  -> 新建 5 个 shopmate-prod_* 卷
docker compose … run --rm migrate                                     -> exit 0，Running upgrade ×4（→ 20261019_0004）
docker compose … up -d api web                                        -> api Healthy、web Healthy
docker compose … ps                                                   -> 7 个容器全部 healthy
exec api /health  -> {"status":"ok"}
exec api /ready   -> {"status":"ready","checks":{"postgres":"ok","redis":"ok","milvus":"ok"}}
curl :8080/healthz -> ok;  curl :8080/ -> <title>ShopMate 电商智能客服</title>
exec api id       -> uid=10001(shopmate) gid=10001(shopmate)
exec api env      -> APP_ENV=production  TRUSTED_HOSTS=127.0.0.1,localhost
docker inspect     -> api/web readonly=true privileged=false CapDrop=[ALL] log=json-file{max-size:10m,max-file:3}
                      （5 个数据服务 readonly=false / privileged=false，符合设计）
```

浏览器实测（Edge，Playwright，`http://127.0.0.1:8080`）：

```text
登录页 title = "ShopMate 电商智能客服"
用户名 shopper01@example.invalid / 演示口令，算式验证码 7 + 2 = ?
POST /api/v1/auth/login -> 200；/auth/me -> 200；/auth/refresh -> 200
登录后 url = http://127.0.0.1:8080/，title = "智能客服 · ShopMate"，role = 消费者
刷新页面后仍在登录态（CSRF cookie Path 重写在生产 nginx 生效）
```

第一次登录曾返回 500，根因是**空库**（`no shop seeded; run scripts/seed.py first`），不是缺陷；
按 §5.1.1 跑 `run --rm seed`、§5.1.3 设演示口令后通过。该现象已写入 `docs/09` §5.1。

另外验证了 P2-3/P2-4 的命令形态：

```text
exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > dump  -> 111,505 字节，exit 0
pg_restore -l（容器内）-> Archive created … TOC Entries: 170，可读
三卷 tar（etcd/minio/milvus 只读挂载）-> 归档顶层目录 = etcd/ milvus/ minio/，与恢复命令的 -C / 对应
```

实跑结束后 `compose … stop`（保留容器与 5 个卷），未执行 `down -v`、未删卷、未删容器；
本机临时 `.env.prod`（本地 tag + 随机口令）已被 `.gitignore` 忽略。

#### 22.7.4 门禁（本轮实测）

```text
uv run ruff check .                                                    -> All checks passed!
uv run pytest tests/unit tests/security -q                              -> 518 passed
uv run pytest -q                                                       -> 600 passed, 2 skipped（基线 591，+9；无删除、无 skip 新增）
uv run python scripts/check_deploy_security.py --strict                 -> 34 项 PASS / 0 WARN / 0 FAIL（exit 0）
docker compose -f compose.prod.yaml --env-file .env.prod.example config --quiet -> exit 0
docker compose config --quiet                                          -> exit 0
uv run python scripts/verify_stage13.py                                 -> 全部一致（0 不一致项），数据集 sha 7606cfce…/136 条
```

跳过项与基线一致：`tests/integration/test_bge_m3_provider.py` 2 条（需 `SHOPMATE_RUN_MODEL_TESTS=1`）。
前端门禁本轮**未重跑**（前端代码零改动，阶段 11/12 记录仍有效）。

#### 22.7.5 阶段 14 复评表（10 项）

| # | 验收项 | 结论 | 证据（命令 → 关键输出） |
|---|---|---|---|
| 1 | 生产编排可校验、变量齐全 | PASS | `docker compose -f compose.prod.yaml --env-file .env.prod.example config --quiet` → exit 0；渲染值 `TRUSTED_HOSTS: 127.0.0.1,localhost,shopmate.example.invalid`、`--forwarded-allow-ips 172.16.0.0/12,…` |
| 2 | 部署安全静态复查（发布门禁） | PASS | `check_deploy_security.py --strict` → 34 PASS / 0 WARN / 0 FAIL，exit 0 |
| 3 | Host 白名单不阻断容器内探针（P1-1） | PASS | `pytest tests/unit/test_trusted_hosts.py -q` → 9 passed（回环 200 / attacker 400 / 仅域名时回环 400）；生产容器 `TRUSTED_HOSTS=127.0.0.1,localhost` 且 api Healthy |
| 4 | 快速开始能给出可登录 UI（P1-2） | PASS | 路径 (a)：`http://127.0.0.1:5173/login` title=ShopMate 电商智能客服 → 登录后 `/`、role=消费者、刷新仍在登录态（2026-10-20T02:41Z）；路径 (c)：`http://127.0.0.1:8080` 同样成功（02:52Z） |
| 5 | PostgreSQL 备份/恢复命令干净 shell 可执行（P2-4） | PASS | `exec -T postgres sh -c 'pg_dump …'` → 111,505 字节 exit 0；`pg_restore -l` → TOC 170 项可读 |
| 6 | Milvus 备份覆盖三卷且恢复有序（P2-3） | PASS（命令实测）/ CONDITIONAL（端到端恢复未演练） | 三卷 tar 成功，归档顶层 = etcd/ milvus/ minio/；恢复步骤与校验命令已写入 §6.4。真实“恢复到空环境”未执行（会清空卷，需单独授权） |
| 7 | 演示脚本可连续执行两次（P2-5） | PASS（文档口径） | `docs/demo.md` §3.3 给出换单 SQL（`order_no`）与三条自检断言；未在浏览器内跑完整两遍 3 分钟脚本 |
| 8 | 生产 api 侧证据（P2-6） | PASS | `migrate` exit 0；7 容器 healthy；`/health` `/ready` 正常；8080 登录成功（role=消费者，刷新后仍登录）；`docker inspect` 只读/非特权/日志轮转全部符合 |
| 9 | 后端门禁不退化 | PASS | ruff 通过；`pytest -q` 600 passed / 2 skipped（基线 591，+9 为新增用例，无删除）；`verify_stage13.py` 全部一致 |
| 10 | 文档一致、无自相矛盾 | PASS | README §4.5/§8/§9/§11 与 docs/08 §2/§6/§10、docs/09 6.3/6.6/§10、docs/demo §3.3/§4 交叉核对；`grep -rn '\$POSTGRES_USER' docs` 无“宿主展开”写法残留 |

#### 22.7.6 未做 / 仍存风险

- **Milvus 端到端恢复演练未做**：三卷备份与归档结构已实测，但“清空三卷 → 恢复 → 检索可用”会破坏数据，
  需单独授权；`docs/08` §6.5 已把“只恢复 PostgreSQL 不算通过”写成硬要求。
- **`ingest`（§5.1.4）未在生产栈执行**：需要 BGE-M3 在容器内加载（数 GB 内存 + 分钟级），
  因此生产栈的“政策问答返回引用”未实测；开发栈该链路此前已由阶段 13 评测与 e2e 覆盖。
- **§7 全量功能烟测（7.1–7.14）未逐条执行**：本轮只做了登录 + 探针；其余旅程依赖既有测试与阶段 13 评测。
- **`TRUSTED_HOSTS` / `FORWARDED_ALLOW_IPS` 的真实取值**取决于边缘代理，静态脚本无法验证，仍需部署时人工确认。
- 生产栈实跑使用**本地 tag 镜像**（`shopmate-api:0.1.0` / `shopmate-web:0.1.0`），未验证私有仓库 push/pull 路径。
- 演示口令仍是固定合成口令（`ShopMate-Demo-Only-2026`），共享环境需 `--password` 覆盖。

#### 22.7.7 复评结论

10 项中 9 项 PASS、1 项 PASS(命令实测)+CONDITIONAL(端到端恢复未演练)。两个 P1 已修复并有回归用例，
4 个 P2 全部落地，P3 的 7/8/9/10 一并完成。门禁全部通过且测试数量未减少。

**阶段 14 验收通过，可以进入阶段 15**（阶段 15 未开始）。
剩余 CONDITIONAL 项属于“需要单独授权的破坏性演练”与“全新主机复核”，不阻塞本阶段验收。

---

## 23. 阶段 15：简历证据与面试材料（2026-10-20）

### 23.1 范围与产出

只做证据整理与材料撰写：**未新增业务功能、未改业务规则、未改评测口径、未提交 Git、未操作容器**。

| 类型 | 文件 | 内容 |
|---|---|---|
| 重写 | `docs/resume-evidence.md` | 证据台账 v2：本人边界、本次复核命令与输出、5 张量化指标证据表（检索/业务/生成/工程/门禁）、实现状态三分表、8 个真实缺陷的定位与修复、禁止表述清单、复核命令 |
| 新增 | `docs/interview-prep.md` | 中文简历项目描述（一句话 / 320 字标准版 / 6 条 bullet / 90 秒口述稿）+ 15 个面试问答提纲（考点·作答·证据·别说）+ 数字速查卡 |
| 修改 | `docs/README.md` | 文档索引补 `interview-prep.md` |
| 修改 | `docs/project-status.md` | 本节（阶段 15 记录） |

未修改 `docs/demo.md`：本阶段无功能与命令变化，演示脚本仍按阶段 14 的 v1.0 执行；改它只会增加不一致风险。

### 23.2 本轮实测（用于替换旧数字，均为亲自运行）

```text
uv run ruff check .                              -> All checks passed!
uv run pytest -q                                 -> 600 passed, 2 skipped（收集 602，138.41s）
uv run pytest tests/security -q                  -> 86 passed
cd frontend && npx vitest --run                  -> 14 files / 124 tests passed
cd frontend && npm run typecheck                 -> 0 错误
uv run python scripts/verify_stage13.py          -> 全部一致（独立复算 == 原始结果）
uv run python scripts/check_deploy_security.py   -> 34 PASS / 0 WARN / 0 FAIL
wc -l / sha256sum 数据集                          -> 136 / 7606cfce…；58 / 856f3338…
grep Aggregated locust u20 / u40                 -> 1350 请求 0 失败 23.0833 req/s；1762 请求 2 失败 29.6058 req/s
git log --oneline                                -> 阶段 15 当时仓库 0 commit（现状见 §0.2：7 个提交）
```

前端 E2E（16 用例）与本机容器启动**本轮未复跑**，台账中已标注"引用阶段 11/12 记录、本轮未复跑"，
不把旧结果写成新结果。

### 23.3 口径澄清（避免后续再次漂移）

1. 测试数量 `591 → 600` 不是"偷偷加测试凑数"：`587`（阶段 12 基线）+ `9`（Host 白名单终版）
   + `4`（生产密钥校验）= `600`，两个文件分别有 9 / 4 个 `def test_`，无删除、无新增 skip。
2. 台账中所有评测数字只有**一个来源**：`stage13-20261020T013230Z.json`；
   各项均标注了分母、样本量与限制（如"58 条/50 条有金标""5 条 answered""单机 CPU"）。
3. `docs/eval-report.md` 里的 0.88 / 0.52 明确写成"5 条上的自评忠实度，且含 2 条哨兵泄漏"，
   台账同步标注，**不得**升级为"政策问答准确率 88%"。

### 23.4 已知问题与风险

- 阶段 15 当时仓库 0 commit（**现状已不同**：2026-10-21 起共 7 个提交、4 个已推送，见 §0.2）；即便如此，证据仍以文件 + 可复算命令为准，commit SHA 只是追加的可追溯项。
- 用户侧若把 `R@1=1.00` 单独引用会被误读（语料仅 27 条有效向量，Milvus `count(*)` 28 含 1 条孤儿、已饱和），台账已在同一行写死限制。
- `NO_EVIDENCE` fail-open（`rag/policy_qa.py`）仍未修，属安全相关缺陷，**已作为"已知缺陷"写进台账与面试提纲**，
  未在简历里隐瞒。
- E2E 与容器实跑未复跑，若面试现场需要演示，须先按 `docs/demo.md` §3 启动环境并重跑。

### 23.5 结论

阶段 15 的三份材料（证据台账、简历描述、面试提纲）均已完成，且每个数字都能落到
`docs/eval-report.md` 的具体小节、原始结果文件或本轮命令输出上。
**状态：完成**。下一阶段（如阶段 16）未开始，本轮未做任何后续阶段的准备性改动。

---

## 23.6 阶段 15 验收整改（2026-10-20 11:24–11:45）

### 23.6.1 背景与范围

2026-10-20 11:17 的只读验收判定 **CONDITIONAL PASS**：唯一阻断项是 `docs/interview-prep.md` Q10 的
数字拆分自相矛盾（7 + 20 + 4 = 31 ≠ 27），另有 4 个 P3 与 1 个非阻断的代码可维护性问题。

本轮**只改文档表述**：不新增功能、不改业务规则、不改评测口径、不改数据集/原始结果、
不改 `rag/policy_qa.py` 的 fail-open、不改 API 契约、不提交 Git、不启停容器、不改 compose 与镜像。

### 23.6.2 整改逐条对照

| # | 文件与位置（整改后行号） | 改前 | 改后 | 对应验收项 |
|---|---|---|---|---|
| 1 | `docs/interview-prep.md` §2 Q10（L174–L187） | 「27 条 refused 里，7 条门槛拦截 + 20 条模型自判 + 4 条未标注引用」= 31 ≠ 27 | 先给 status 分布 **answered 5 / handoff 4 / refused 27（5+4+27=36）**；27 拆成 **7 条证据门槛拦截 + 20 条模型自判（7+20=27）**；**4 条未标注引用属 handoff（`uncited_claim`），不计入 refused**；证据行补原始结果 `parts.policy_llm.status_counts` 与逐条 `reasons` 计数 | P2 阻断项 |
| 2 | `docs/interview-prep.md` Q3（L104）、数字速查卡（L251）、`docs/resume-evidence.md` §4.1（L88）、`docs/eval-report.md` 2.4.3（L355）与 2.9.4（L653） | 口径混用：「27 条有效向量」与未标 `count(*)` 的「28 条」并存，2.4.3 结论句只写「28 条」不注含义 | 统一为 **「27 条有效向量（Milvus `count(*)` 28，含 1 条孤儿）」**；2.9.4 的历史引文改为「Milvus `count(*)` 28」+「27 条有效向量」，**27 / 28 两个原始值均未改动** | P3-1 |
| 3 | `README.md` §12（L309–L310） | 文档表缺两份阶段 15 文档 | 按 `docs/README.md` 顺序补 `docs/resume-evidence.md`、`docs/interview-prep.md` 两行 | P3-2 |
| 4 | `docs/demo.md` §3.4 演示前自检（L128–L133） | 只有「政策问答能返回引用」一条 | 补两条：① 本地 `qwen2.5:7b`（**历史基线**，2026-10-23 起改为 DeepSeek）可答率仅 **5/29（0.1724）**，现场返回「证据不足」按已知模型保守解释，改为展示「检索命中 + 引用字段」而非反复追问；② 若 `NO_EVIDENCE [c1]…` 被当答案返回，属已知 fail-open（`rag/policy_qa.py` 哨兵精确相等判定），**不得当场解释成「系统会正确拒答」** | P3-3 |
| 5 | `docs/project-status.md` §22.5（L1280–L1283）、§23.4（L1478） | 「未启动生产栈」与 §22.7 实跑记录冲突；§23.4 仍写「27 条向量」 | §22.5 加**补注**：生产栈已在 §22.7 实跑（`migrate` exit 0 / 7 容器 healthy / 8080 登录成功），**历史结论不改**，仅「未在全新主机复核 checklist」仍成立；§23.4 统一为 27 条有效向量 + `count(*)` 28 含 1 孤儿 | P3-4、P3-1 |
| 6（可选，未改代码） | `docs/resume-evidence.md` §8（L266–L269） | 单跑 `tests/unit/test_query_rewrite.py` 会因 `db/repositories/knowledge.py` 循环导入 collect 失败，文档未提 | 在复核命令下加说明：**单跑该文件需先导入 `db.repositories.knowledge`**；全量收集 602 不受影响。**未改 Python**，避免为可维护性问题引入回归 | 可选项 |

**附带修正（交叉引用纠错，不涉及任何数字）**：fail-open 的正文章节是 `docs/eval-report.md` §2.9.0，
而 2.5.2 的表格与 `docs/demo.md` §3.4 原指向「2.9.1 的 #0 项」（其余三份文档本已指向 2.9.0）。
本轮统一改为 **§2.9.0**，避免演示现场按错误章节找不到依据。

### 23.6.3 复核输出（本轮实测）

```text
uv run python scripts/verify_stage13.py
  -> 全部一致（独立复算 == 原始结果）          退出码 0
     status_counts recomputed={'answered': 5, 'handoff': 4, 'refused': 27} claimed=同值  [OK]
     milvus={'rows_count_star': 28, 'matched_pg_chunks': 27, 'orphan_count': 1, 'pg_chunks_not_indexed': 21}

wc -l data/eval/eval_questions.jsonl data/eval/retrieval_cases.jsonl
  -> 136 / 58
sha256sum 同上
  -> 7606cfceb6ad101c…（136 条）/ 856f3338d00b8c44…（58 条）       与整改前一致，未被覆盖

grep -n "refused|handoff" docs/interview-prep.md
  -> L177 answered 5 / handoff 4 / refused 27（5 + 4 + 27 = 36）
     L178 27 条 refused 拆成两块：7 条门槛拦截 / 20 条模型自判（7 + 20 = 27）
     L180–L181 4 条 uncited_claim 属 handoff，不属于 refused
     L186–L187 原始结果 status_counts 与 reasons 逐条计数

grep -rn "27 条有效向量|28 条" docs
  -> 命中项全部为「27 条有效向量」；未标注 `count(*)` 含义的裸「28 条」表述已为 0 处

grep -rn "2\.9\.1 #0" docs
  -> 0 处（fail-open 引用已统一为 §2.9.0）

uv run pytest -q
  -> 600 passed, 2 skipped, 26 warnings in 137.27s        （收集 602，与阶段 15 基线一致）
```

四份文档（`resume-evidence.md` / `interview-prep.md` / `eval-report.md` / `project-status.md`）交叉核对
`600 passed` / `0.1724（5/29）` / `0.6324（86/136）` / `0.7059` / `7/7` / `0.8182` / `23.08→29.61`，
逐项 grep 结果一致，无互相矛盾的表述。

### 23.6.4 结论

5 条整改全部完成并通过复核，1 条可选项以「文档注明」方式关闭（未改代码）。

**阶段 15 验收通过，项目可以进入最终演示/交付。**
未修的 `NO_EVIDENCE` fail-open 仍留在 `rag/policy_qa.py`（属业务逻辑变更，需所有者单独授权），
已作为已知缺陷写进台账 §5.2、面试 Q4 与演示自检 §3.4，不构成验收阻断项。

下一阶段（阶段 16）**未开始**，本轮未做任何后续阶段的准备性改动；未提交 Git；未启停容器。

---

## 24. 阶段 16：最终收尾（2026-10-20）

### 24.1 范围与授权

本轮只处理 4 个已确认遗留项（W1 Git 基线、W2 后端端点补齐、W3 fail-open、W4 收尾验证与文档），
**不新增产品功能、不做重构、不改评测口径**。所有者已通过任务单显式授权 W1–W4。

未做且仍需单独授权的事项（与本轮无关）：`git push` / 打 tag、启停或重建容器、清 Milvus 卷、
drop/truncate 数据库、修改 `data/eval/` 下的数据集与原始结果、修改 gate 阈值或已对外数字。

### 24.2 W1 · Git 基线

开工时仓库 **0 commit**（`git log` 报 `does not have any commits yet`），全部文件未跟踪，
因此没有任何回滚点。本轮建立两个提交：

```text
1bae45dc8479cd0d1d106b27b96cefc64d0d5eeb  docs: 补齐阶段 0-15 文档与评测证据
f81159b605b30db00d3754aa91dac2f4da77b58c  chore: 建立仓库基线（源码/测试/脚本/前端/编排/配置模板）

git status --short   -> （空）
git ls-files | wc -l -> 358
git ls-files | grep -E "^models/|(^|/)\.env$" | wc -l -> 0
```

`.gitignore` 核对结果：`.venv/`、`node_modules/`、`frontend/dist/`、`models/`（2.2 GB BGE-M3 权重）、
`.env` / `.env.*`（保留 `!.env.example`、`!.env.prod.example`）、`__pycache__/`、`.pytest_cache/`
均已覆盖；`data/`（4.9 MB）与 `data/eval/results/`（4.4 MB 评测证据）**未**被忽略，按预期入库。

本轮只对 `.gitignore` 追加两行（均为"运行时产物不应入库"）：

```text
.workbuddy/tmp/            # agent 一次性脚本；.workbuddy/memory 仍入库
data/knowledge/uploads/    # POST /admin/documents 的落盘目录
```

敏感信息扫描（对暂存索引执行，命中项逐条人工确认）：

| 模式 | 命中 | 结论 |
|---|---|---|
| `BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY` | 1 处，`docs/final-wrapup-prompt.md` 的**任务说明文字** | 非密钥 |
| `sk-…` / `AKIA…` | 0 | — |
| `shopmate-dev-` | `core/config.py` 默认值 + 文档/测试说明 | 占位符，且 `ensure_production_secrets()` 在 production 拒绝 |
| `postgresql://user:pass@` | `.env.example`（`replace-with-…`）、`alembic.ini`（`change-me-local-only`）、compose 的 `${POSTGRES_PASSWORD}`、测试假串 | 全为占位符 |

### 24.3 W2 · 补齐 4 组后端端点

**契约差异结论（只加不删）**：`docs/06-api.md` §12/§13 的其余字段现有表都已具备，
唯一缺的是 `handoff_tickets.resolution_summary` / `close_reason` 两个字段与一张质量标记表，
因此迁移只做 `ADD COLUMN` + `CREATE TABLE`，**不改任何已有列类型、不回填历史语义**。

| 层 | 文件 | 改动 |
|---|---|---|
| 迁移 | `alembic/versions/20261020_0005_final_wrapup_support_admin.py` | 新增 2 列 + `support_quality_labels` 表（含 `label` CHECK、`(shop_id,message_id,labeled_by)` 唯一） |
| 模型 | `db/models/support.py`、`db/models/__init__.py` | `HandoffTicket` 加 2 字段；新增 `SupportQualityLabel` |
| 仓储 | `db/repositories/support.py`（新） | 队列（风险→等待时长排序）、详情、`assign/resolve/close` 状态机（`SELECT … FOR UPDATE`，非法转换抛 `InvalidTicketTransition`）、会话取证（要求授权工单）、质量标记 upsert |
| 仓储 | `db/repositories/knowledge_admin.py` | `create_uploaded_document`、`edit_chunk`、`soft_delete_chunk`、`create_ingestion_job`、`load_ingest_target` |
| 路由 | `api/support.py`（新）、`api/admin.py` | 5 个客服端点；上传/`PATCH`+`DELETE` chunk/`reindex` |
| 装配 | `main.py` | 注册 support 路由与 OpenAPI tag；把已装配的 BGE-M3 实例复用给 `ingestion_runner` |
| 解析复用 | `rag/ingest/pipeline.py`、`rag/ingest/worker.py`（新） | `ingest_source` 增加 4 个**可选**显式 id（默认 `None` → 行为不变），worker 用它重解析上传创建的同一版本 |
| 错误码 | `core/errors.py`、`api/errors.py` | 补 `FILE_TOO_LARGE`(413)、`UNSUPPORTED_FILE_TYPE`(415)、`UNSAFE_FILE`(400) |
| Schema | `api/schemas.py` | §12/§13 的请求/响应模型（`action` 与字段匹配校验、`text`/`is_enabled` 至少一项） |

关键安全/边界决定：

1. **权限沿用现有 code**，不新增：`support:ticket:read/write`、`support:conversation:read`、
   `support:quality_label:write`。`admin` 默认不含这些 → 客服端点对 admin 返回 403（契约 §12 要求）。
2. **会话取证必须有授权工单**：没有关联工单的会话一律 404，不提供"列出全部消费者会话"。
3. **响应脱敏**：`user_reference_masked` / `assigned_to_masked` 取自 `users.display_name_masked`，
   缺失时用 `user-****<id 后 2 位>`；消息正文再过一遍 `mask_pii()`；不返回系统 prompt、堆栈、密钥。
4. **写操作全部审计**：`support.ticket.assign/resolve/close`、`support.quality_label.write`、
   `admin.document.upload`、`admin.chunk.update/disable`、`admin.document.reindex` 各写一条 `audit_events`。
5. **上传门禁**：扩展名白名单（PDF/DOCX/PPTX/MD/TXT）、20 MiB 上限、魔数校验
   （`%PDF-` / `PK\x03\x04`）、文本必须 UTF-8 且无 NUL、文件名拒绝 `..` 与路径分隔符、落盘重命名。
6. **解析语义如实**：上传/重建索引只落 `queued` 的 `ingestion_jobs` + `parse_status=pending`。
   进程装配了 BGE-M3 时由 `ingestion_runner` 在后台调用 `ingest_source` 解析；未装配（CI、无权重机）
   时 job 保持 `queued`——不写成"已解析"。

实测（本节命令均在改动后实际执行）：

```text
uv run alembic upgrade head
  -> Running upgrade 20261019_0004 -> 20261020_0005      当前 = 20261020_0005 (head)
information_schema 核对
  -> handoff_tickets 新增列 = close_reason / resolution_summary
  -> support_quality_labels 表存在 = 1

uv run pytest tests/integration/test_support_api.py -q          -> 13 passed
uv run pytest tests/integration/test_ingest_worker.py -q        -> 1 passed
uv run pytest tests/unit/test_support_contract.py -q            -> 14 passed
```

覆盖的验收点：队列字段与 §12 逐字一致；消费者/admin/匿名分别 403/403/401；跨店工单 404 且与
"不存在"完全同构；`resolve` 从 `open` 触发 `409 INVALID_STATE`；`resolve` 缺 summary 为 `400`；
跨店 assignee `403`；会话取证 200 且正文无完整手机号、`admin` 403；质量标记越权 404、同客服重复标记
只保留一条；上传 202 + `pending` + job `queued` + 出现在列表；伪造 PDF 415、路径穿越 400；
chunk 编辑 `reindex_required=true` 且 hash 变化、软删后 `is_enabled=false`。

### 24.4 W3 · 修 `NO_EVIDENCE` fail-open

`rag/policy_qa.py` 新增 `sentinel_of()`：剥离 `[cN]` 标签 → 去首尾空白 → 去句末标点 → 忽略大小写比对；
`answer()` 与 `citation_label_issues()` 都改用它。**归一步骤放在标签校验之前**，否则
`CONFLICT [c1][c2]` 会先报 `unknown_citation:c2` 而掩盖"模型其实拒绝了"。

```text
uv run pytest tests/unit -k sentinel -q   -> 10 passed
```

`tests/unit/test_policy_sentinel.py` 覆盖 5 类输入：`NO_EVIDENCE`→refused、`NO_EVIDENCE [c1]`→refused、
`conflict。`→handoff、`NO_EVIDENCE[c1].`→refused、正常带标签答案→answered（不误伤），
另有一条"金额承诺仍被拦截"防止过度归一化。**未重跑全量评测**，历史数字仍对应修复前行为，
`docs/eval-report.md` §2.9.0 已加"已修（阶段 16）"注记与口径声明。

### 24.5 W4 · 门禁与烟测

```text
uv run ruff check .                                  -> All checks passed!
uv run pytest -q                                     -> 638 passed, 2 skipped（两次全量复跑：143.92s / 139.30s）
uv run python scripts/verify_stage13.py              -> 全部一致（0 不一致项），exit 0
uv run python scripts/check_deploy_security.py       -> 34 PASS / 0 WARN / 0 FAIL，exit 0
cd frontend && npm run typecheck                     -> 0 错误（前端本轮零改动）
```

测试增量（600 → 638，**+38，无删除、无新增 skip**）：`tests/unit/test_support_contract.py` 14 条、
`tests/integration/test_support_api.py` 13 条、`tests/integration/test_ingest_worker.py` 1 条、
`tests/unit/test_policy_sentinel.py` 10 条。两条既有断言随 schema 变化同步更新（非放宽）：
`test_migrations.py` 的 head → `20261020_0005`，`test_openapi_contract.py` 的路径/操作数 30→36、34→43、
需要 401/403 的操作 26→35。

`docs/09-release-checklist.md` §7 逐条（本轮只做到"能证明的"）：

| # | 结果 | 说明 |
|---|---|---|
| 7.1 注册 / 7.2 登录 | 未验证（UI） | 代码路径由 `tests/integration/test_api_flow.py` 覆盖，本轮未开浏览器 |
| 7.3 商品搜索 / 7.4 比较 / 7.5 政策问答 / 7.6 无证据拒答 | 未验证 | 需 BGE-M3 + LLM；本轮不启停容器 |
| 7.7 订单 / 7.8 越权 / 7.9 退货 / 7.10 幂等 / 7.11 转人工 | 未验证（UI） | 同上；API 层由既有集成测试覆盖 |
| 7.12 多会话 | 通过（API 层） | `GET /api/v1/conversations` → 200 |
| 7.13 管理端 | 通过（API 层） | 文档 21 条、知识库 3 条；上传/片段编辑由集成测试证明（202 + `pending`） |
| 7.14 客服端 | 通过（API 层） | 队列 20 条；消费者 403；admin 403 |

烟测脚本：`scripts/smoke_stage16.py`（进程内 ASGI + 真实开发库，未启停容器，只读）。

### 24.6 仍剩什么

- **未在全新主机按 README 从零复核**（`docs/09` §0–§6 全链路）：本轮沿用既有开发栈，未重建环境。
- **Milvus 三卷未做端到端恢复演练**：清卷属破坏性操作，仍需单独授权。
- **官方 `ragas` 包未运行**：报告里的 faithfulness/relevancy 是自建 LLM-as-judge 代理。
- **上传后的解析只在"有 BGE-M3 的进程"里发生**：CI/无权重机只验证到 `queued`；
  `ingestion_runner` 在真实模型下的端到端入库未在本轮实测（`test_ingest_worker.py` 用 fake embedder 证明 id 复用与状态流转）。
- **7.1–7.11 的浏览器端烟测未重跑**（如上表），依赖既有 e2e 与阶段 13 评测记录。
- `docs/eval-report.md` §2.9.1 的其余失败项（意图路由兜底、商品对比名称解析、
  `PRODUCT_FACT` 工具分派、退货 `order_item_id`）**未修**，仍按原文记录。

### 24.7 结论

W1–W4 全部完成：仓库有了基线（2 个 commit）、客服工作台与管理端写接口闭环（含迁移、审计、脱敏、
状态机与上传门禁）、唯一的安全类 fail-open 已修并有回归测试、门禁全绿且测试只增不减。

阶段 16 **完成**，项目可以进入最终演示/交付。§24.6 的 5 项属"需要单独授权的破坏性演练"
或"未重跑的 UI 烟测"，不构成阻断。

### 24.8 回答模型接入 DeepSeek + 提示词格式约束（2026-10-20 下午）

**背景**：`.env` 配置 `LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-v4-flash`
后，DeepSeek 调用本身 **200 OK**、检索正常（8 条引用），但政策答案被引用校验判为
`uncited_claim`，用户侧只看到"已转人工"。

**根因（与模型厂商无关，任何模型都可能触发）**：`citation_label_issues()` 用
`(?<=[。！？；\n])` 切句，**分号也算句子边界**。模型习惯写「甲；乙 [c1]。」，
切出的「甲；」没有引用 → 整条答案作废。阶段 13 的 4 条 `uncited_claim` 同源。

**处置**：只改 `SYSTEM_PROMPT` 的格式约束（业务规则与校验阈值均未动）：

- 第 9 条扩写为禁止 Markdown（`**`/`#`/`-`/表格）；
- 新增第 10 条：只输出自然段落，不要标题行、不要「一、二、三」/「1. 2. 3.」分节；
- 新增第 11 条：**禁止用分号连接分句**，每个分句单独成句、各自在句号前标 `[cN]`。

**实测**（`deepseek-v4-flash`，同一问题"七天无理由怎么退？"）：

```text
修复前：assistant 内容 35 字 = "这次生成的回答无法逐条对应到知识库引用…"，引用 8 条但正文被丢弃
修复后：assistant 内容 507 字，引用 c1–c5，逐句带标签，结构自然（结论 → 操作 → 退款 → 大促）
```

**口径影响**：历史评测（阶段 13）是在旧提示词下跑的，与本次格式约束**不可直接对比**；
本轮未重跑评测，`scripts/verify_stage13.py` 仍对应旧结果（exit 0，未改动）。

**回退**：`.workbuddy/backup/prompt-20261020-1620/policy_qa.py.bak`，
或 `git checkout -- src/shopmate_ecommerce_assistant/rag/policy_qa.py`（注意该文件在本轮
还包含 W3 的 `sentinel_of()` 修复，回退会一并丢掉）。

---

## 25. 阶段 17：功能补齐与前端改版（2026-10-22）

> 触发：用户反馈「界面不好看、对话答非所问且机械、转人工后无法处理、商品太少、没有下单/退款/退货」。
> 范围：前端视觉与交互、对话质量、工单闭环、商品目录、自助交易。**未提交 git、未重启容器**。

### 25.1 变更清单

| 领域 | 变更 |
| --- | --- |
| 商品目录 | 30 → **62 个商品 / 104 个 SKU**，新增鞋服箱包、家居、厨电、个护、运动、宠物、食品等品类 |
| 对话质量 | 预算解析（元→分）、品类同义词、多轮主题继承、品类过滤、**LLM 只在事实底稿上改写语气**（数字不新增、失败回退模板） |
| 意图路由 | 新增 `purchase`、`refund_status`；`product_fact` 允许 `search_products`；修正「便宜点」被误判为资金决策 |
| 退货 | 聊天里真实执行 `check_return_eligibility`（按订单号 + 商品名匹配 order_item），不再永远返回澄清 |
| 下单/支付/取消 | `POST /orders`、`POST /orders/{id}/pay`、`POST /orders/{id}/cancel`；支付时行锁扣库存，取消回滚 |
| 退款 | 新表 `refund_requests` + `POST/GET /refunds`；客服 `GET /support/refunds`、`POST /support/refunds/{id}/review` |
| 工单闭环 | `POST /support/tickets/{id}/reply` 写回原会话；消费者聊天页 8 秒低频轮询看到「人工客服」回复 |
| 卡片持久化 | `messages.cards_jsonb`（迁移 0007），重开历史会话仍能看到商品卡片 |
| 前端 | 设计系统重写、登录页/聊天页/商品中心/订单/退款/客服台全部改版；新增结算页与「我的退款」 |
| 演示数据 | `scripts/demo_orders.py`：2 天前签收订单（可演示退货）+ 待支付订单（可演示支付/取消） |
| 稳健性 | 策略文档写入增加重试（Windows 文件锁导致的 `OSError 22`）；搜索注入噪声词过滤，全噪声查询返回空而非全量 |

### 25.2 实测证据（2026-10-22）

```text
alembic upgrade head            → 20261020_0005 → 0006 → 0007 成功
pytest (unit+integration+security, 独立库 shopmate_test)
                                → 637 passed, 2 skipped, 1 error*
                                → 该 error 为 Windows docx 文件锁；加写入重试后
                                  tests/integration/test_api_security.py + test_seed_data.py
                                  → 29 passed
ruff check src tests scripts alembic → All checks passed
frontend: vue-tsc --noEmit     → 0 errors
frontend: vitest --run         → 123 passed (14 files)
frontend: vite build           → built in 10.20s
```

\* 全量 637 passed 与阶段 16 的 638 相差 1：新增的 `test_api_security` 上传用例在文件锁下未执行；
加写入重试后该文件 29 条全部通过。评测口径与数字**未改动**，`verify_stage13.py` 未重跑。

### 25.3 端到端手测（本机 uvicorn :18003 + vite :5174）

- 下单 → 支付 → 退款申请 → 客服审批 → 消费者看到 `approved` + 审核说明：通过
- 客服工单回复 → 消费者会话内出现「人工客服」消息：通过
- 聊天：「预算300以内的降噪耳机」返回 3 款耳机；「有没有便宜点的」继承上一轮主题按价格升序；
  「订单 SM-2026-00901 能退吗」返回真实资格结论；「我的退款到哪了」返回本人退款
- 截图见 `docs/screenshots/`（chat / products / order-detail / support）

### 25.4 已知限制

- 生产栈的 `shopmate-api` 容器仍在 `Restarting (255)`：镜像内缺少 `20261020_0005` 迁移文件，
  需要重建镜像（`docker compose build api`）后才能启动；本轮按约定未启停/重建容器。
- 退款审批只有「通过/拒绝」两步，没有打款重试、对账与退款单导出。
- 聊天里的下单仍是引导到商品页，不在对话内直接创建订单（写操作需要显式确认，保持人机边界）。

## 26. 阶段 18–20：课程任务书补齐与图片扩展（2026-10-23，未提交）

> 这三项都不在原始 16 阶段计划里，来自课程任务书与可选扩展。代码已在工作区，**未提交 git**；
> 详细契约在 `docs/06-api.md`，评测口径在 `docs/eval-report.md` §3.8 与新增 §5。

### 26.1 阶段 18：会话级知识库多选

- 存储：`conversations.knowledge_base_ids_jsonb`（迁移 `20261023_0008`，空数组 = 不限制）。
- 端点：`GET /api/v1/knowledge-bases`（登录用户、本店 + active）、
  `PATCH /api/v1/conversations/{id}/knowledge-bases`（`[]` = 全部）。
- 检索：`RetrievalScope.knowledge_base_ids` → Milvus `knowledge_base_id in [...]` + PostgreSQL 复核；
  显式选择时放开隐式 locale/region 收窄，空选择保持 `zh-CN/CN`。
- 跨店/停用/不存在的库统一 `422 KNOWLEDGE_BASE_NOT_SELECTABLE`，整单拒绝，不落部分选择。
- 回归：`tests/unit/test_retrieval_kb_filter.py`；E2E `frontend/e2e/knowledge-bases.spec.ts`。

### 26.2 阶段 19：对话页推理参数面板

- 存储：`conversations.generation_params_jsonb`（迁移 `20261023_0009`）。
- 端点：`GET /api/v1/generation-defaults`、`PATCH /api/v1/conversations/{id}/generation-params`
  （合并语义：缺省不变、显式 `null` 清除）。
- 模型调用：`AnswerModel.complete(..., generation=)` 注入 temperature/top_p/max_tokens，
  `history_turns` 打到 `recent_history(limit=…)`；`max_tokens` 超 `LLM_MAX_TOKENS_CAP` 直接 400，不静默截断。
- 前端：`GenerationParamsPanel.vue`（拖动改草稿、松手/回车才 PATCH、失败回滚）+ ChatView 顶栏弹层。

### 26.3 阶段 20：图片文档 OCR 与原图回源（可选扩展）

- 支持 `.png/.jpg/.jpeg`：Pillow 校验真伪与尺寸（≤10 MiB、≤4000 万像素）+ RapidOCR 离线识别
  → 文本块入库，检索/引用/护栏零改动。
- 元数据：`metadata_jsonb.image = {filename, format, width, height, ocr_lines, ocr_mean_confidence, image_url}`；
  引用事件新增 `image_url/image_filename/image_width/image_height`（文本文档为 `null`）。
- 原图回源：`GET /api/v1/knowledge-images/{document_id}`（登录 + 同店 + 仅图片 + 路径必须在知识目录内，
  否则 404 `DOCUMENT_NOT_FOUND`）。
- 语料与金标：新增 1 张渲染截图（`scripts/seed.py` 可重现）与 `image-01..03` 三条金标，金标 140 → 143。

### 26.4 本轮门禁（2026-10-23 实测）

```text
uv run pytest -q                     -> 804 passed, 2 skipped
uv run ruff check .                  -> All checks passed!
cd frontend && npm run typecheck     -> 0 errors
cd frontend && npx vitest --run      -> 149 passed (16 files)
uv run python scripts/eval_retrieval.py --output data/eval/results/retrieval-image-20261023.json
                                     -> 图片类 hit@3 3/3、hit@1 2/3、MRR 0.8333（hybrid）
```

未做：`scripts/verify_stage13.py` 未按 143 条重跑（§3.3 的 140 条口径原样保留，见 eval-report §3.8 的口径说明）；
前端 E2E 仅跑了 `knowledge-bases` 与 `chat-generation` 两条，其余 16 条未复跑。
