# ShopMate 部署与运维手册（阶段 14）

> 适用版本：0.1.0  
> 关联文件：`compose.yaml`（开发/演示）、`compose.prod.yaml`（生产）、`web/Dockerfile.prod`、`web/nginx.prod.conf`、`.env.prod.example`  
> 契约依据：AGENTS.md §14；`docs/03-architecture.md`；`docs/07-security.md`

本手册只描述**已经存在并可验证**的东西。凡是尚未实现的端点或流程，都在 §12 明确标注，不写成“已完成”。

---

## 1. 部署拓扑

```text
                 Internet
                    │  HTTPS（443）
                    ▼
        ┌───────────────────────────┐
        │ 边缘代理 / LB（TLS 终结）  │   ← 不在本仓库，由部署方提供
        └──────────────┬────────────┘
                       │ HTTP 8080
                       ▼
        ┌───────────────────────────┐        internal network
        │ web (nginx, 非 root)      │ ─────────────┐
        │ 静态资源 + /api 反代      │              │
        └──────────────┬────────────┘              │
                       │ http://api:8000           │
                       ▼                           │
        ┌───────────────────────────┐              │
        │ api (uvicorn, 单 worker)  │──────────────┤
        │ FastAPI + BGE-M3(挂载只读)│              │
        └───┬────────┬────────┬─────┘              │
            │        │        │                    │
            ▼        ▼        ▼                    │
      PostgreSQL   Redis   Milvus ── etcd / MinIO ─┘
      (named vol) (named vol) (named vol)
```

- **唯一对外端口**：`web` 的 `8080`（可用 `WEB_PORT` 改）。API、数据库、向量库、对象存储均不映射宿主端口。
- **TLS 必须在边缘终结**：容器内只跑 HTTP。边缘代理需要转发 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto`，并允许 SSE 长连接（读超时 ≥ 5 分钟）。
- **单副本**：MVP 不支持水平扩展，原因见 §14。

---

## 2. 开发栈与生产栈的差异

| 维度 | `compose.yaml`（开发/演示） | `compose.prod.yaml`（生产） |
|---|---|---|
| 项目名/数据卷 | `shopmate` | `shopmate-prod`（卷完全隔离，互不污染） |
| 对外端口 | API 8000、Web 3000、PG 5432、Redis 6379、Milvus 19530/9091、MinIO 9000/9001 | 仅 Web 8080 |
| 进程 | Uvicorn 默认参数（容器无 reload；仅宿主机本地开发用 `--reload`） | `--no-access-log --workers 1 --proxy-headers`，无 reload |
| 用户 | 镜像内已是非 root（UID 10001 / nginx） | 同镜像 + `read_only` + `cap_drop: ALL` + `no-new-privileges` |
| 迁移 | API 容器启动命令里 `alembic upgrade head` | 独立一次性 `migrate` 服务；API 等它成功后再启动 |
| 资源限制 | 无 | 每个服务 `deploy.resources.limits`（CPU/内存） |
| 日志 | 默认 json-file 无上限 | json-file，`max-size=10m`、`max-file=3` |
| 镜像 | 本地 build，tag `shopmate-api:0.1.0` / `shopmate-web:0.1.0` | `${API_IMAGE}`/`${WEB_IMAGE}` 指向不可变 tag 或 digest；**编排不含 `build` 段**，镜像必须先由构建机/CI 产出（§3.1） |
| 密钥 | `.env` 占位符 | `.env.prod` 强制注入（`${VAR:?}`，缺失即启动失败） |
| 前端产物 | `web/public` 占位页（阶段 4 脚手架），**不是消费者界面**，见 README §4.5 | `web/Dockerfile.prod` 从 `frontend/` 构建真实 Vue 产物 |
| 数据初始化 | 允许 `scripts/seed.py` | `seed`/`ingest` 放在 `tools` profile，不随 `up` 启动 |

---

## 3. 前置条件

| 项 | 要求 |
|---|---|
| 主机 | Linux（或 Docker Desktop + WSL2）；≥ 4 vCPU、≥ 8 GB 内存（建议 16 GB）、≥ 20 GB 磁盘 |
| Docker | 24+，Compose v2.20+（实测 29.8 / v5.5） |
| 模型权重 | 主机目录 `./models/bge-m3`（约 2.3 GB），只读挂载到 `/models` |
| 边缘代理 | 负责 TLS、域名、可能的 WAF；需支持 SSE |
| 镜像仓库 | 可推送/拉取 `shopmate-api`、`shopmate-web` 的私有仓库（可选，也可本机构建） |

### 3.1 构建镜像

```bash
# API 镜像（非 root、无 reload、不含权重）
docker build -t shopmate-api:0.1.0 .

# 生产前端镜像（Node 构建 Vue → Nginx 非 root 运行）
docker build -f web/Dockerfile.prod -t shopmate-web:0.1.0 .

docker tag shopmate-api:0.1.0 registry.example.invalid/shopmate/api:0.1.0
docker tag shopmate-web:0.1.0 registry.example.invalid/shopmate/web:0.1.0
docker push registry.example.invalid/shopmate/api:0.1.0
docker push registry.example.invalid/shopmate/web:0.1.0
```

**受限网络**（无法直连 Docker Hub）时，用 build-arg 把基础镜像换成内网镜像：

```bash
docker build -f web/Dockerfile.prod \
  --build-arg NODE_IMAGE=registry.internal/library/node:22.22.2-alpine \
  --build-arg NGINX_IMAGE=registry.internal/library/nginx:1.27.5-alpine \
  -t shopmate-web:0.1.0 .
```

基础镜像默认固定到 digest（`node:22.22.2-alpine@sha256:8ea2…`、`nginx:1.27.5-alpine@sha256:6564…`）。替换时同样要固定 tag 或 digest，禁止 `latest`。

**没有私有仓库时**：把 `.env.prod` 的 `API_IMAGE` / `WEB_IMAGE` 直接设为本地 tag
（`shopmate-api:0.1.0` / `shopmate-web:0.1.0`）。只要 tag 不是 `latest`，`check_deploy_security.py` 就会通过。

> 生产编排**没有 `build` 段**：`docker compose -f compose.prod.yaml build` 不会构建任何东西，
> 镜像只能来自上面的 `docker build` 或 CI 推送。这样做是为了保证“生产只运行不可变镜像”，
> 避免在服务器上现场编译出与流水线不一致的镜像。开发栈 `compose.yaml` 仍保留 `build`。

---

## 4. 首次部署

### 4.1 准备配置

```bash
cp .env.prod.example .env.prod
# 必须替换：POSTGRES_PASSWORD / REDIS_PASSWORD / MINIO_ROOT_PASSWORD /
#           JWT_SECRET / TOOL_TOKEN_SECRET / API_IMAGE / WEB_IMAGE /
#           API_CORS_ORIGINS（真实域名）/ TRUSTED_HOSTS（真实域名 + 保留 127.0.0.1,localhost）
```

生成强随机值：

```bash
LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40; echo
```

> `.env.prod` 已被 `.gitignore` 忽略。`docker compose config` 会把变量渲染为明文，**不要把它贴进工单或聊天**。

### 4.2 校验编排

```bash
docker compose -f compose.prod.yaml --env-file .env.prod config --quiet
```

缺失 `API_IMAGE`、`POSTGRES_PASSWORD`、`JWT_SECRET` 等变量会直接报错——这是有意设计，避免“空口令启动”。

### 4.3 启动依赖

```bash
docker compose -f compose.prod.yaml --env-file .env.prod up -d postgres redis etcd minio milvus
docker compose -f compose.prod.yaml --env-file .env.prod ps
```

**数据影响**：首次执行会创建 5 个 named volume（`shopmate-prod_*`）；不会触碰开发栈的 `shopmate_*` 卷。

等待 `postgres`、`redis`、`etcd`、`minio`、`milvus` 全部 `healthy`（Milvus 首启约 30–60 秒）。

### 4.4 执行迁移

```bash
docker compose -f compose.prod.yaml --env-file .env.prod run --rm migrate
```

**数据影响**：只做 schema 变更（建表/加列/索引），不写业务数据。迁移失败时容器以非 0 退出，API 不会启动（`depends_on: service_completed_successfully`）。

迁移前先备份（§6）。Alembic 版本不保证可回退：`downgrade` 只在本地演练过，生产以“备份 + 前向修复”为主。

### 4.5 启动应用

```bash
docker compose -f compose.prod.yaml --env-file .env.prod up -d api web
docker compose -f compose.prod.yaml --env-file .env.prod ps
```

**端口**：只有 `web` 映射 `${WEB_PORT:-8080}:8080`。API 通过 `http://api:8000` 供 web 反代，宿主与公网都访问不到。

### 4.6 健康验证

```bash
# Web（容器内）
docker compose -f compose.prod.yaml --env-file .env.prod exec web \
  wget -q -O - http://127.0.0.1:8080/healthz

# API 存活 + 依赖就绪
docker compose -f compose.prod.yaml --env-file .env.prod exec api \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
docker compose -f compose.prod.yaml --env-file .env.prod exec api \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"

# 对外（经边缘代理或本机端口）
curl -s http://127.0.0.1:8080/healthz
```

期望：`/health` 返回 `{"status":"ok"}`；`/ready` 返回 `{"status":"ready","checks":{"postgres":"ok","redis":"ok","milvus":"ok"},...}`。

> **这两个命令为什么能通过**：它们请求 `http://127.0.0.1:8000`，Host 头就是 `127.0.0.1`，
> 因此 `TRUSTED_HOSTS` **必须**包含 `127.0.0.1`（以及 `localhost`）。模板默认值是
> `127.0.0.1,localhost,shopmate.example.invalid`，编排兜底默认值是 `127.0.0.1,localhost`。
> 若只填公网域名，`/health` 会返回 `400 Invalid host header`，api 永久 unhealthy，
> web 因 `depends_on: service_healthy` 起不来。这一点由 `tests/unit/test_trusted_hosts.py`
> 的两条用例（回环 200 / attacker 400）固定住。

### 4.7 知识入库（生产必需）

```bash
# 源文件来自仓库内 data/knowledge（只读挂载），写入 PostgreSQL 元数据 + Milvus 向量
docker compose -f compose.prod.yaml --env-file .env.prod run --rm ingest
```

**数据影响**：新增 `knowledge_versions` / `knowledge_chunks` 行与 Milvus collection 数据；幂等（同内容不重复建版本）。需要 `./models/bge-m3` 存在，否则进程直接失败并给出权重路径错误。

图片文档（阶段 20）走本地 OCR（`rapidocr-onnxruntime`，模型随 wheel 打包），入库时同样产生 chunk 与向量，
不需要额外的 OCR 服务或外网。镜像里的 `fonts-noto-cjk` 只服务于 `seed` 渲染合成截图；纯 ingest 不需要字体。

> `seed`（合成数据）**只用于演示/预发**：它会写 `data/` 目录与业务表。生产环境不要执行。

---

## 5. 日常操作

| 操作 | 命令 |
|---|---|
| 查看状态 | `docker compose -f compose.prod.yaml --env-file .env.prod ps` |
| 查看日志（尾 200 行） | `docker compose -f compose.prod.yaml --env-file .env.prod logs --tail=200 api` |
| 跟踪日志 | `... logs -f web` |
| 重启单个服务 | `... restart api` |
| 停止（保留卷） | `... down` |
| 灰度发布 API | 构建新 tag → 改 `API_IMAGE` → `... up -d api` |
| 进入容器排查 | `... exec api sh`（只读文件系统，无法写盘） |
| 查看资源占用 | `docker stats --no-stream` |

**禁止**：`docker compose down -v`、`docker volume rm`、`docker system prune --volumes`。这些会删除数据卷，且不经确认不得执行。

---

## 6. 备份与恢复

### 6.1 备份对象

| 对象 | 位置 | 丢失后果 | 备份方式 |
|---|---|---|---|
| PostgreSQL | 卷 `shopmate-prod_postgres_data` | 订单、退货、工单、知识元数据、评测记录全丢 | `pg_dump -Fc`（首选） |
| Milvus 向量数据 | **三卷**：`${COMPOSE_PROJECT_NAME}_milvus_data` + `_minio_data` + `_etcd_data`（segment 本体在 MinIO） | 检索不可用（collection 存在也是空结果） | 三卷一起快照（§6.4 路径 A），或由 PostgreSQL + 源文档重建（路径 B） |
| 知识源文件 | `data/knowledge/` | 无法重建知识库 | 随代码仓库/对象存储备份 |
| 配置 | `.env.prod`、`compose.prod.yaml` | 无法复现部署 | 密钥管理器 + Git（`.env.prod` 不入库） |
| BGE-M3 权重 | `./models/bge-m3` | 无法重建向量、政策问答降级 | 单独归档或重新下载 |

### 6.2 PostgreSQL 逻辑备份

> **变量从哪里来**：`POSTGRES_USER` / `POSTGRES_DB` 是 **postgres 容器内**的环境变量，宿主 shell 里通常为空
> （`.env.prod` 没有被 `export`）。因此所有命令都用 `exec -T postgres sh -c '...'` 让容器自己展开变量；
> 写成 `pg_dump -U "$POSTGRES_USER"` 会在干净 shell 里展开成空串并直接失败。

```bash
# 备份：容器内展开变量，宿主只接收字节流
docker compose -f compose.prod.yaml --env-file .env.prod exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "shopmate-pg-$(date -u +%Y%m%dT%H%M%SZ).dump"

# 校验：文件非空 + TOC 可读（问题在这里暴露，而不是等到恢复时）
ls -l shopmate-pg-*.dump
pg_restore -l shopmate-pg-20261020T020000Z.dump | head
```

建议：每日一次全量 + 保留 14 天；迁移和大版本发布前额外打一次。

### 6.3 PostgreSQL 恢复

```bash
# 1) 停应用，避免写入竞争
docker compose -f compose.prod.yaml --env-file .env.prod stop api web

# 2) 恢复（--clean 会先删对象，属于破坏性操作，务必确认目标库）
docker compose -f compose.prod.yaml --env-file .env.prod exec -T postgres \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < shopmate-pg-20261020T020000Z.dump

# 3) 校验 alembic 版本与关键表行数（同样在容器内展开变量）
docker compose -f compose.prod.yaml --env-file .env.prod exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "select version_num from alembic_version;" \
    -c "select count(*) from orders;" \
    -c "select count(*) from knowledge_chunks;"'

# 4) 重新启动
docker compose -f compose.prod.yaml --env-file .env.prod start api web
```

### 6.4 Milvus 备份与恢复（三卷，缺一不可）

Milvus standalone 的数据分布在三个卷里，**只备份 `milvus_data` 无法恢复检索**：

| 卷 | 内容 | 丢失后果 |
|---|---|---|
| `${COMPOSE_PROJECT_NAME}_etcd_data` | collection/schema/segment 元数据与 checkpoint | Milvus 认为没有 collection |
| `${COMPOSE_PROJECT_NAME}_minio_data` | segment / binlog / index 的实际对象（向量本体在这里） | collection 存在但检索为空或报 segment 不存在 |
| `${COMPOSE_PROJECT_NAME}_milvus_data` | WAL、缓存与本地状态 | 恢复后可能无法回放到一致状态 |

**路径 A：三卷快照（推荐，需短暂停写）**

```bash
# 卷名前缀取自 .env.prod 的 COMPOSE_PROJECT_NAME，不硬编码
PROJ=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env.prod | tail -1); PROJ=${PROJ:-shopmate-prod}

# 备份：先停写（api + milvus），再一次性打包三卷
docker compose -f compose.prod.yaml --env-file .env.prod stop api milvus
mkdir -p backup
docker run --rm \
  -v "${PROJ}_etcd_data:/etcd:ro" \
  -v "${PROJ}_minio_data:/minio:ro" \
  -v "${PROJ}_milvus_data:/milvus:ro" \
  -v "$PWD/backup:/backup" \
  alpine sh -c 'tar czf "/backup/milvus-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C / etcd minio milvus'
docker compose -f compose.prod.yaml --env-file .env.prod start milvus api
```

```bash
# 恢复：顺序固定 etcd → minio → milvus，最后才起 api
PROJ=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env.prod | tail -1); PROJ=${PROJ:-shopmate-prod}
ARCHIVE="$PWD/backup/milvus-20261020T020000Z.tar.gz"

# 1) 停写
docker compose -f compose.prod.yaml --env-file .env.prod stop api milvus

# 2) 清空并解包三卷（破坏性操作：必须已有可用备份、已确认卷名、已得到同意）
docker run --rm \
  -v "${PROJ}_etcd_data:/etcd" \
  -v "${PROJ}_minio_data:/minio" \
  -v "${PROJ}_milvus_data:/milvus" \
  -v "$(dirname "$ARCHIVE"):/backup:ro" \
  alpine sh -c "rm -rf /etcd/* /minio/* /milvus/* && tar xzf /backup/$(basename "$ARCHIVE") -C /"

# 3) 先 etcd + minio → 再 milvus → 等 healthy → 最后 api
docker compose -f compose.prod.yaml --env-file .env.prod up -d etcd minio
docker compose -f compose.prod.yaml --env-file .env.prod up -d milvus
docker compose -f compose.prod.yaml --env-file .env.prod ps     # etcd/minio/milvus 均 healthy
docker compose -f compose.prod.yaml --env-file .env.prod up -d api web
```

**恢复后校验（三条都要过）**

```bash
# a) Milvus collection 行数 > 0（api 镜像内含 pymilvus，借用它的网络位置）
docker compose -f compose.prod.yaml --env-file .env.prod exec -T api python -c \
  "from pymilvus import MilvusClient; print(MilvusClient(uri='http://milvus:19530').get_collection_stats('shopmate_knowledge_chunks'))"

# b) PostgreSQL 知识片段行数 > 0
docker compose -f compose.prod.yaml --env-file .env.prod exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from knowledge_chunks"'

# c) 一次政策问答能返回引用：浏览器打开 http://<host>:${WEB_PORT:-8080}，登录后问
#    “七天无理由怎么退？”，在 DevTools → Network → chat/stream 里确认流中出现
#    event: citation，且含 document_id / 章节 / 版本 / 生效日期 / 片段 ID。
```

**路径 B：从源文档重建（无需备份向量，作为兜底）**

向量是 `data/knowledge` 与 PostgreSQL 元数据的派生数据，可完整重建：

```bash
# 重建 collection 并全量重导入（会 DROP 现有 collection，属破坏性操作）
docker compose -f compose.prod.yaml --env-file .env.prod run --rm ingest
# 或在宿主机（能连到 Milvus 时）
uv run python scripts/rebuild_knowledge_index.py --yes
uv run python scripts/rebuild_knowledge_index.py --verify-only   # 校验 sparse 覆盖率/维度/归一化
```

重建耗时取决于文档数量与 CPU 性能，需按实际环境测量，本手册不给未实测的分钟数。

### 6.5 备份演练要求

- 每季度至少一次“从备份恢复到空环境”演练，记录：备份时间、恢复耗时、`/ready` 结果、抽样查询结果。
- PostgreSQL 与 **Milvus 三卷**都要演练；只恢复 PostgreSQL 不算通过（检索会不可用）。
- 恢复后必须验证：`alembic_version` 为 head、订单/知识片段行数非 0、Milvus collection 行数非 0、
  政策问答能返回引用。
- 演练失败的结论必须写进 `docs/project-status.md`，不能只在聊天里说“恢复了”。

---

## 7. 安全复查（阶段 14）

### 7.1 自动复查

```bash
uv run python scripts/check_deploy_security.py           # 表格输出
uv run python scripts/check_deploy_security.py --json    # 机器可读
```

检查项（34 项，全部 PASS 才算通过）：

| 组 | 检查内容 |
|---|---|
| 容器权限 | 两份编排均无 `privileged`、无 `network_mode: host`、无 `docker.sock` 挂载 |
| 应用硬化 | `api`/`web` 具备 `read_only` + `tmpfs`、`cap_drop: ALL`、`no-new-privileges` |
| 资源与日志 | 7 个常驻服务均有 CPU/内存上限与 `max-size/max-file` |
| 网络暴露 | 数据服务与 API 不映射宿主端口 |
| 镜像 | 无 `latest`；Dockerfile 非 root、无 `--reload` |
| 密钥 | `.env.example`/`.env.prod.example` 敏感键全为占位符；git 未跟踪 `.env`；生产编排无内联口令 |
| PII | `data/`、`docs/`、env 样例未命中手机号/身份证/银行卡模式（测试夹具不在扫描范围） |

### 7.2 人工确认项

- 边缘代理是否只允许 HTTPS，并设置 HSTS、请求体上限、SSE 超时。
- `API_CORS_ORIGINS` 与 `TRUSTED_HOSTS` 是否与真实域名完全一致（不带通配符）；`TRUSTED_HOSTS` 需额外保留 `127.0.0.1,localhost` 供容器内探针使用。
- `FORWARDED_ALLOW_IPS` 是否只覆盖内网/容器网段（不含 `*`），与边缘代理实际来源一致。
- `.env.prod` 是否只存在于服务器与密钥管理器，没有进入镜像层、日志或工单。
- 备份文件是否加密存放，访问权限是否受限。
- `docker inspect` 抽查：`ReadonlyRootfs=true`、`Privileged=false`、无 `docker.sock` 挂载。

```bash
docker inspect --format '{{.Name}} readonly={{.HostConfig.ReadonlyRootfs}} privileged={{.HostConfig.Privileged}}' \
  $(docker ps -q --filter "name=shopmate-prod")
```

### 7.3 本阶段实测结果

见 `docs/07-security.md` §18（命令、输出摘要、仍存风险）。

---

## 8. 故障与恢复

| 现象 | 可能原因 | 诊断 | 恢复 |
|---|---|---|---|
| `api` 反复重启，日志含 `password authentication failed` | `.env.prod` 口令与卷内初始口令不一致（卷已用旧口令初始化） | `... logs api \| tail -50`；`... exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select 1"'` | 改回原口令，或用 `ALTER USER` 重置；**不要删卷** |
| `migrate` 退出码非 0 | 迁移脚本冲突 / 数据库不可达 / 权限不足 | `... run --rm migrate` 前台重跑看堆栈 | 修复后重跑；迁移失败时 API 不会启动，属预期 |
| `/ready` 返回 503 且 `milvus: error` | Milvus 未就绪或 etcd/MinIO 异常 | `... logs --tail=100 milvus`；`... ps` | 等 Milvus healthy；检查 `etcd`/`minio` 状态 |
| 政策问答固定回“知识库暂不可用” | 权重未挂载 / 加载失败 / collection 为空 | `... logs api \| grep -i "RAG wiring"`；`... exec api ls /models/bge-m3` | 挂载权重；执行 §4.7 入库 |
| 页面能开，接口全 502 | `api` 未 healthy 或 web 反代地址变更 | `... ps`；`... exec web wget -qO- http://api:8000/health` | 先修 api；web 依赖 `service_healthy` |
| 登录 429 | 认证限流（默认 10 次/分钟/IP）+ 边缘限流 30 次/分钟 | 响应头/日志中的 429 | 等待窗口；按需调 `RATE_LIMIT_AUTH_PER_MINUTE` 与 nginx `limit_req` |
| 登录成功但刷新后回到登录页 | 反向代理未放行/未重写 cookie Path，或跨域访问 | 浏览器 DevTools 看 `shopmate_csrf` 是否存在、Path 是否为 `/` | 保持同源访问；确认使用 `web` 端口而不是直连 API |
| SSE 首包很慢/成批到达 | 中间代理开了 buffering | 对比直连 `api` 与经 web 的行为 | 边缘代理关闭 buffering，读超时 ≥ 5 分钟 |
| 上传 413 | 超过 `client_max_body_size 25m` 或应用上限 20 MB | 看 nginx 日志 | 调整上限（两侧都要改） |
| 容器启动即 `read-only file system` | 进程试图写根文件系统 | `... logs` 中的路径 | 把该路径挂到 `tmpfs`（参考 `HOME`/`HF_HOME`/`TORCH_HOME`） |
| 内存持续上涨 / OOMKilled | BGE-M3 加载 + 长上下文 | `docker stats`；`dmesg \| grep -i oom` | 提高 `API_MEMORY_LIMIT`；限制并发；不要开多 worker |
| 磁盘写满 | 日志/卷增长 | `docker system df` | 日志已轮转；检查备份目录与 Milvus 卷 |

**通用原则**：先看 `ps` 与 `logs`，再决定是否重启；重启无效时保留现场（`docker inspect`、日志片段）再动手。任何删除卷的操作都必须先备份并得到明确同意。

---

## 9. 升级与回滚

1. **备份**：`pg_dump` + 记录当前镜像 tag。
2. **构建/拉取新镜像**：新 tag（如 `:0.1.1`），不改动运行中的容器。
3. **迁移**：`... run --rm migrate`（迁移必须向后兼容一个版本，便于回滚）。
4. **切换**：更新 `.env.prod` 的 `API_IMAGE`/`WEB_IMAGE` → `... up -d api web`。
5. **验证**：`/health`、`/ready`、登录、一次聊天、一次政策问答。
6. **回滚**：把镜像 tag 改回上一个版本并 `up -d`；若新迁移不兼容旧代码，则用 §6.3 恢复备份。

前端回滚独立于后端：`WEB_IMAGE` 指回旧 tag 即可（静态资源带内容哈希，无缓存污染）。

---

## 10. 配置项速查

| 变量 | 作用 | 默认 | 生产建议 |
|---|---|---|---|
| `APP_ENV` | 运行环境标识 | `demo` | `production`（编排已固定） |
| `DATABASE_URL` | asyncpg 连接串 | 本地占位 | 由编排拼接，勿手写 |
| `REDIS_URL` | Redis 连接串 | 本地占位 | 同上 |
| `MILVUS_URI` / `MILVUS_HEALTH_URL` | 向量库地址/健康检查 | `localhost` | 编排内为 `http://milvus:19530` |
| `JWT_SECRET` | 访问令牌签名 | 开发占位 | 40 位随机，轮换即全端下线 |
| `TOOL_TOKEN_SECRET` | 退货资格令牌签名 | 开发占位 | 40 位随机 |
| `API_CORS_ORIGINS` | 允许的浏览器来源 | `http://localhost:3000` | 真实 https 域名，禁用 `*` |
| `TRUSTED_HOSTS` | Host 头白名单（空=不校验） | 空 | **必须含 `127.0.0.1,localhost` + 公网域名**；只填域名会让容器内 `/health` 探针 400 |
| `FORWARDED_ALLOW_IPS` | 可信代理来源（`--forwarded-allow-ips`） | `172.16.0.0/12,10.0.0.0/8,192.168.0.0/16,127.0.0.1` | 限定内网/容器网段；**禁止 `*`** |
| `RATE_LIMIT_AUTH_PER_MINUTE` | 认证接口限流 | 10 | 按真实流量调整 |
| `RATE_LIMIT_CHAT_PER_MINUTE` | 聊天限流 | 20 | 同上 |
| `SSE_KEEPALIVE_SECONDS` / `SSE_TOTAL_TIMEOUT_SECONDS` | SSE 心跳与总时长 | 15 / 120 | 与边缘代理超时匹配 |
| `EMBEDDING_MODEL_PATH` | 权重目录 | `models/bge-m3` | 容器内 `/models/bge-m3` |
| `EMBEDDING_DIMENSION` | dense 维度 | 1024 | 改动必须重建 collection |
| `POLICY_MIN_EVIDENCE_SIMILARITY` | 证据门槛 | **0.62**（`.env` / `.env.example` / 两个 compose / 本文档一致） | 按 140 条金标 dev 划分标定（2026-10-23 金标增至 143 条后**阈值未改**）；0.42 仅作宽松演示档（无答案问题会被答出来，严格拒答 7/7 → 0/7），任何指标对比都用 0.62 |
| `LLM_PROFILE` | 回答模型档位 | `deepseek` | 只填空缺：`deepseek` / `qwen`（课程任务书对齐）/ `local`（Ollama，**仅离线烟测，不作评测基线**）；显式 `LLM_BASE_URL`/`LLM_MODEL` 优先级更高 |
| `LLM_BASE_URL` / `LLM_MODEL` | 回答模型端点 | `https://api.deepseek.com` / `deepseek-flash` | 生产、开发、评测统一 DeepSeek；`deepseek-v4-flash` 只是网关别名（不在 `/models` 列表） |
| `LLM_API_KEY` | 回答模型密钥 | 空 | **只走环境变量或 secret 管理器**；留空则政策问答退回"只给引用 + 明确拒答" |
| `LLM_TIMEOUT_SECONDS` / `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | 调用参数 | 60 / 0.1 / 0 | `LLM_MAX_TOKENS=0` 表示不发送该参数、沿用供应商默认 |

> 2026-10-23 口径统一：`POLICY_MIN_EVIDENCE_SIMILARITY` 此前编排默认 0.42、代码/评测 0.62，现已全部改为 **0.62**；若确要放宽到 0.42 做演示，README §7 写明了差异与适用场景（只是演示，不能用于指标对比）。

---

## 11. 容量与性能边界

- **单 worker 硬约束**：BGE-M3 在进程内单例加载，多 worker 会重复占用数 GB 内存；`uvicorn --workers 1` 是刻意设置。需要更高吞吐时，先拆独立 embedding 服务，再扩 API 副本。
- **CPU 推理**：检索延迟主要在向量化；首次请求会触发模型加载（冷启动慢），健康检查只看 `/health`，不看首个查询耗时。
- **SSE 并发**：每条流占一个连接与一个请求上下文；nginx `worker_connections 1024`，实际瓶颈在 API 侧数据库连接与内存。
- **资源上限**：`api` 默认 2 CPU / 6 GB，`milvus` 2 CPU / 3 GB，`postgres` 2 CPU / 2 GB；低于此规格会导致 OOM 或明显超时，需按机器调整 `API_CPU_LIMIT` / `API_MEMORY_LIMIT`。
- **压测数据**见 `docs/eval-report.md`（Locust 结果只覆盖响应头，不覆盖 SSE 全链路）。

---

## 12. 已知缺口（部署视角）

| 缺口 | 影响 | 当前替代方案 |
|---|---|---|
| 客服工作台需 `support:*` 权限 | 用 `admin01` 打开 `/support` 会 403（admin 默认不含 support 权限） | 用 `support01`；验证：`uv run python scripts/smoke_stage16.py`（阶段 16 起 `/support/*` 已注册） |
| 上传/重建索引只落 `queued` job | 实例未装配 BGE-M3 时文档停在 `pending`，需有权重的进程解析 | 阶段 16 起接口已实现；用 `scripts/ingest.py` 或具备 BGE-M3 的实例继续 |
| ~~无 Prometheus 指标端点~~ 已补（2026-10-24） | `GET /metrics` 暴露聊天轮次/延迟、LLM token/延迟、检索延迟、转人工与拒答计数。生产由 `compose.prod.yaml` 强制要求 `METRICS_TOKEN`，抓取侧带同值 Bearer 头或 `X-Metrics-Token`；本地默认开放，共享主机时必须设置 | 验证：`curl -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8000/metrics`；指标定义在 `src/.../observability/metrics.py` |
| 无自动备份任务 | 依赖人工/外部 cron | 按 §6.2 配置宿主机 cron + 对象存储 |
| 无多副本/滚动更新 | 发布有秒级中断 | 低峰发布；后续可加负载均衡与共享 embedding 服务 |

这些缺口在 `README.md` §9 与 `docs/06-api.md` 中有对应标注，不在演示中隐藏。
