# 全新环境启动检查清单（阶段 14）

> 用途：在一台**没有本项目任何残留**的机器上，按顺序验证“照文档能不能跑起来”。
> 每一项都有：命令、预期结果、失败时看哪里。全部勾选才算通过。
> 生产方式一律用 `compose.prod.yaml`；本地开发用 `compose.yaml`，差异见 §2。

**约定**

- `$PROD="docker compose -f compose.prod.yaml --env-file .env.prod"`（bash 可先导出，下面为可读性写全）。
- 标注 **⚠️ 数据影响** 的步骤会创建或修改数据，执行前确认目标环境。
- 任何一步失败，**不要**通过删卷、关鉴权、放宽断言来“跑通”。

---

## 0. 主机前置

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 0.1 | Docker 可用且是 Linux 容器 | `docker info --format '{{.ServerVersion}} {{.OSType}}'` | 版本号 + `linux` |
| 0.2 | Compose 版本 | `docker compose version` | v2.20+（实测 v5.5） |
| 0.3 | 端口未被占用 | `docker ps --format '{{.Names}} {{.Ports}}'` | 没有进程占用 `${WEB_PORT:-8080}` |
| 0.4 | 磁盘 | `df -h .` | 可用 ≥ 20 GB |
| 0.5 | 内存 | `docker info --format '{{.MemTotal}}'` | ≥ 8 GB（建议 16 GB） |
| 0.6 | 模型权重 | `ls models/bge-m3/config.json` | 文件存在（缺失时政策问答降级，不阻塞启动） |
| 0.7 | Python / uv（宿主机工具链） | `uv --version && uv run python -V` | uv 0.12.x / Python 3.12 |

---

## 1. 配置

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 1.1 | 复制模板 | `cp .env.prod.example .env.prod` | 文件存在，权限 `600` |
| 1.2 | 替换全部占位符 | `grep -nE 'replace-with|example\.invalid' .env.prod` | 只应剩域名类占位符（若用真实域名则无输出） |
| 1.3 | `.env.prod` 未被跟踪 | `git check-ignore -v .env.prod` | 输出命中 `.gitignore` |
| 1.4 | 编排语法 | `docker compose -f compose.prod.yaml --env-file .env.prod config --quiet` | 无输出、退出码 0 |
| 1.5 | 镜像引用已填 | `docker compose -f compose.prod.yaml --env-file .env.prod config \| grep image:` | 无 `latest`，无空值 |

---

## 2. 镜像

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 2.1 | 构建 API | `docker build -t shopmate-api:0.1.0 .` | 退出码 0，镜像非 root（`USER 10001`） |
| 2.2 | 构建 Web | `docker build -f web/Dockerfile.prod -t shopmate-web:0.1.0 .` | 退出码 0，产物来自 `frontend/` 构建 |
| 2.3 | 推送/打 tag | `docker tag shopmate-web:0.1.0 $WEB_IMAGE && docker push $WEB_IMAGE` | 推送成功（离线环境可跳过，改用本地 tag） |
| 2.4 | API 镜像无权重 | `docker run --rm shopmate-api:0.1.0 ls /models` | 目录不存在或为空（权重只挂载） |

---

## 3. 依赖服务

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 3.1 | 启动依赖 ⚠️ 创建 5 个卷 | `docker compose -f compose.prod.yaml --env-file .env.prod up -d postgres redis etcd minio milvus` | 5 个容器创建 |
| 3.2 | 健康状态 | `docker compose -f compose.prod.yaml --env-file .env.prod ps` | 5 个服务 `healthy`（Milvus 首启 30–60s） |
| 3.3 | 数据服务未暴露端口 | `docker ps --format '{{.Names}} {{.Ports}}' \| grep shopmate-prod` | 只有 web 有宿主端口映射 |
| 3.4 | PostgreSQL 可连 | `... exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select 1"'` | 返回 `1` |
| 3.5 | Redis 可连 | `... exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'` | `PONG` |

---

## 4. 迁移

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 4.1 | 执行迁移 ⚠️ 改 schema | `... run --rm migrate` | 退出码 0，日志含 `Running upgrade` |
| 4.2 | 版本为 head | `... exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version"'` | 与 `alembic/versions/` 最新版本一致 |
| 4.3 | 核心表存在 | `... exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'` | 含 `orders`、`return_requests`、`handoff_tickets`、`knowledge_chunks` |

---

## 5. 数据

### 5.1 演示/预发

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 5.1.1 | 合成数据 ⚠️ 写 `data/` 与业务表 | `... run --rm seed` | 输出各表计数与数据集指纹 |
| 5.1.2 | 幂等 | 再跑一次 5.1.1 | 计数不变 |
| 5.1.3 | 演示账号 ⚠️ 改 3 行口令哈希 | `... run --rm seed python /app/scripts/demo_accounts.py` | 输出 3 个账号 `password-set`/`unchanged` |
| 5.1.4 | 知识入库 ⚠️ 写 Milvus | `... run --rm ingest` | 逐文档输出 `ready`，退出码 0 |
| 5.1.5 | 向量校验 | 宿主机 `uv run python scripts/rebuild_knowledge_index.py --verify-only` | sparse 覆盖率 100%，dense 1024 维 |

> `tools` profile 服务（`seed`/`ingest`）挂载了 `scripts/` 与 `data/`，因此可以直接覆盖 command 运行其他脚本；
> 若在能连到数据库的宿主机上操作，也可用 `DATABASE_URL=... uv run python scripts/demo_accounts.py`。
>
> **Windows / Git Bash 注意**：`run --rm seed python /app/scripts/...` 会被 MSYS 改写成宿主路径
> （报 `can't open file 'E:/.../app/scripts/...'`）。加 `MSYS_NO_PATHCONV=1` 前缀即可，或把脚本路径写成 `//app/scripts/...`。
>
> **空库登录会 500**：刚 `migrate` 完的库里没有 shop 行，`POST /api/v1/auth/login` 返回
> `INTERNAL_ERROR`（日志为 `no shop seeded; run scripts/seed.py first`）。这是数据未就绪，
> 先跑 §5.1.1，再跑 §5.1.3 设演示口令。

### 5.2 生产

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 5.2.1 | 不执行 seed | — | 生产禁止合成数据写入 |
| 5.2.2 | 知识入库（真实源文件） | 将文档放入 `data/knowledge/` 并更新 `manifest.json`，再 `... run --rm ingest` | 版本创建成功，`parse_status=ready` |
| 5.2.3 | 抽查片段 | `... exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from knowledge_chunks"'` | 行数 > 0 |

---

## 6. 启动应用

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 6.1 | 启动 | `... up -d api web` | 两个容器 `running` |
| 6.2 | 状态 | `... ps` | `api`/`web` 均 `healthy` |
| 6.3 | 存活探针 | `... exec api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())"` | `{"status":"ok"}`。**前提**：`.env.prod` 的 `TRUSTED_HOSTS` 含 `127.0.0.1,localhost`；只填公网域名时这里返回 `400 Invalid host header`，6.2 永远不会 healthy |
| 6.4 | 就绪探针 | 同上，路径改 `/ready` | `{"status":"ready","checks":{"postgres":"ok","redis":"ok","milvus":"ok"}}` |
| 6.5 | Web 健康 | `curl -s http://127.0.0.1:${WEB_PORT}/healthz` | `ok` |
| 6.6 | 前端页面 | 浏览器打开 `http://<host>:${WEB_PORT}/` | 看到 ShopMate 登录页（不是阶段 4 占位页）。**只在用 `web/Dockerfile.prod` 构建的 `${WEB_IMAGE}` 下成立**；开发栈 `compose.yaml` 的 web 是 `web/public` 占位页，看真实 UI 走 README §4.5 的 (a) 或 (b) |
| 6.7 | OpenAPI（仅容器内） | `... exec api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/docs').status)"` | `200`。注意：`/docs` **不经** web 反代暴露，公网访问不到，属预期 |

---

## 7. 功能烟测

| # | 场景 | 操作 | 预期 |
|---|---|---|---|
| 7.1 | 注册 | 打开 `/register`，填邮箱 + 密码 + 算式验证码 | 201/成功，自动登录或跳登录页 |
| 7.2 | 登录 | `shopper01@example.invalid` / 演示口令 | 进入聊天页，右上角显示角色 |
| 7.3 | 商品搜索 | 输入“预算 300 元以内、适合通勤的降噪耳机” | 商品卡片含价格、SKU、库存、`as_of` |
| 7.4 | 商品比较 | 输入“比较这两款的降噪和续航” | 字段对齐，缺失为 unknown |
| 7.5 | 政策问答 | 输入“七天无理由怎么退？” | 回答 + 引用（文档/章节/版本/生效期/片段 ID） |
| 7.6 | 无证据拒答 | 输入“火星地区支持无人机配送吗？” | 明确无依据，不编造条款 |
| 7.7 | 订单 | 输入自己的 `SM-2026-*` 订单号 | 状态、金额、物流节点、更新时间 |
| 7.8 | 越权 | 输入他人订单号 | 统一拒绝，不泄露归属 |
| 7.9 | 退货申请 | 资格检查 → 确认创建 | `submitted`，提示“申请不等于退款” |
| 7.10 | 幂等 | 用同一幂等键重复提交 | 不产生第二条申请 |
| 7.11 | 转人工 | 输入“我要投诉并起诉，要求立刻赔偿” | 风险标签 + 工单 ID，无资金承诺 |
| 7.12 | 多会话 | 新建/重命名/删除会话 | 列表即时更新，删除为软删除 |
| 7.13 | 管理端 | `admin01` 登录后打开知识库页 | 列表可加载；上传一个 `.md`（≤20 MiB）返回 `202` + `parse_status=pending`，片段编辑返回 `reindex_required=true`（阶段 16 起可用；解析由具备 BGE-M3 的进程执行） |
| 7.14 | 客服端 | `support01` 登录后打开工单页 | 工单队列正常加载，列表项字段与 `docs/06-api.md` §12 一致；打开工单详情可看到状态流转按钮。消费者与 `admin` 访问 `/api/v1/support/tickets` 均返回 `403`（阶段 16 起可用） |

> 7.5 依赖知识入库与 BGE-M3 权重；未完成 §5.1.4 时该项应显示“知识库暂不可用”，这属于**环境未就绪**而不是缺陷。

---

## 8. 安全与运维

| # | 检查 | 命令 | 预期 |
|---|---|---|---|
| 8.1 | 静态安全复查 | `uv run python scripts/check_deploy_security.py` | 34 项 PASS、0 FAIL |
| 8.2 | 只读根文件系统 | `docker inspect --format '{{.Name}} {{.HostConfig.ReadonlyRootfs}}' $(docker ps -q --filter name=shopmate-prod)` | api/web 为 `true` |
| 8.3 | 无特权 | `docker inspect --format '{{.Name}} {{.HostConfig.Privileged}}' $(docker ps -q --filter name=shopmate-prod)` | 全部 `false` |
| 8.4 | 无 socket 挂载 | `docker inspect --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' $(docker ps -q --filter name=shopmate-prod)` | 无 `docker.sock` |
| 8.5 | 日志轮转 | `docker inspect --format '{{.Name}} {{.HostConfig.LogConfig.Options}}' $(docker ps -q --filter name=shopmate-prod)` | 含 `max-size:10m`、`max-file:3` |
| 8.6 | 日志无密钥 | `... logs --tail=500 api \| grep -iE 'password|secret|token='` | 仅可能出现字段名，无真实值 |
| 8.7 | 路由隔离 | `... exec api python -c "..."`（或 `curl` 直连 8000 不可达） | 宿主无法直连 api 端口 |
| 8.8 | 备份已配置 | `crontab -l \| grep pg_dump` | 存在每日备份任务 |
| 8.9 | 恢复演练记录 | — | 最近一次演练日期与结果已写入 `docs/project-status.md` |

---

## 9. 发布签字

| 项 | 负责人 | 时间 | 结果 |
|---|---|---|---|
| 环境与镜像 | | | |
| 迁移与数据 | | | |
| 功能烟测 | | | |
| 安全复查 | | | |
| 备份与回滚预案 | | | |

**回滚预案（必须提前写好）**

1. 记录本次发布的两个镜像 tag（上一个 / 当前）。
2. 迁移前已生成 `pg_dump`，文件路径：`________`。
3. 回滚命令：改 `.env.prod` 的 `API_IMAGE`/`WEB_IMAGE` → `... up -d api web` → 跑 §6.3–6.5。
4. 若迁移不兼容旧代码：`stop api web` → §6.3 恢复备份 → 启动旧镜像。

---

## 10. 本清单的实测记录

| 日期 | 环境 | 结果 | 备注 |
|---|---|---|---|
| 2026-10-20 | 本机 Windows + Docker 29.8 / Compose v5.5（开发栈运行中） | 部分通过 | 完成编排校验、安全复查、前端生产镜像构建、健康检查；未在全新主机上执行完整 5.1–7.14（避免影响现有数据卷），详见 `docs/project-status.md` §22 |
| 2026-10-20（整改后复评） | 本机，生产栈实跑（独立 `shopmate-prod` 卷） | 通过（§0–§4、§6、§8 实测；§7 部分） | `migrate` 退出码 0；7 个容器全部 healthy（api/web `read_only`）；`/health` `/ready` 正常；`8080` 用 `shopper01` 登录成功（角色=消费者，刷新后仍在登录态）；`docker inspect` 显示 `ReadonlyRootfs=true`、`Privileged=false`、日志 `10m×3`。§5.1 seed 与 §5.1.3 演示口令已执行；§5.1.4 ingest 与 §7 全量烟测未做（见 §22.7） |
| 2026-10-20（阶段 16 收尾） | 本机 Windows + 开发栈容器（PG/Redis/Milvus 运行中），API 走进程内 ASGI（未启停容器） | 部分通过（§7 的 7.12–7.14 API 层 + §8.1 实测） | `uv run python scripts/smoke_stage16.py` → 7.12/7.13/7.14 全 PASS（support01 工单队列 20 条、admin 文档 21 条、消费者与 admin 访问 `/support/tickets` 均 403）；`check_deploy_security.py` 34 PASS / 0 FAIL；§7.1–7.11 与 7.13/7.14 的**浏览器 UI** 未重跑（需前端 dev server 与 BGE-M3，本轮不启停容器）；详见 `docs/project-status.md` §24 |
