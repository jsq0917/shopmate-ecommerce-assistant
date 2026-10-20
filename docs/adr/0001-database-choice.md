# ADR-0001：主数据库选择 PostgreSQL 16

- 状态：已接受
- 日期：2026-10-18
- 阶段：阶段 3
- 相关文档：`docs/03-architecture.md`、`docs/04-data-contract.md`

## 背景

课程电商 RAG 示例使用 MySQL，但 ShopMate 的 MVP 同时需要：

- 商品、SKU、库存、订单、物流、退货、工单和知识版本之间的强关系与事务一致性。
- JSONB 属性过滤，同时限制业务搜索只能使用白名单字段。
- UUID、复合外键、partial unique index、检查约束和版本有效期索引。
- 与 SQLAlchemy 2.x async、Alembic 和 Docker Compose 的可复现集成。

`AGENTS.md` 已固定 PostgreSQL 16。本 ADR 记录该决定及其与课程 MySQL 的差异，防止后续实现悄悄切换数据库。

## 决策

ShopMate 的唯一主数据库使用 **PostgreSQL 16**，由 Docker Compose 管理。ORM 使用 SQLAlchemy 2.x async，所有 schema 变化使用 Alembic 迁移。

具体规则：

1. UUID 作为主键；金额使用 `BIGINT *_cents` 加 ISO 4217 币种。
2. 时间使用 `TIMESTAMPTZ`，存 UTC 瞬时。
3. 商品扩展属性、规则摘要、配置和审计摘要使用受控 JSONB，不使用任意 SQL 或不受限 JSON 查询。
4. 使用复合唯一约束/外键绑定 `shop_id` 和用户归属，防止跨租户关系拼接。
5. 使用 partial unique index 阻止同一订单项存在多个有效退货申请。
6. 使用 `pg_trgm` 等受控索引辅助商品标题/品牌搜索；任何查询都参数化，不拼接用户 SQL。
7. Redis 只作缓存/限流；Milvus 只作向量检索；二者都不是业务事实的唯一权威源。

## 与课程 MySQL 的差异

| 维度 | 课程 MySQL 示例 | ShopMate |
|---|---|---|
| 主数据库 | MySQL | PostgreSQL 16 |
| 结构化事实 | MySQL/业务表 | PostgreSQL + 受控 Redis/Mock OMS |
| 扩展属性 | MySQL JSON | 受控 JSONB + 参数化过滤 |
| 复杂约束 | MySQL 约束/应用层 | 复合 FK、CHECK、partial unique index |
| 迁移 | 示例代码/脚本 | Alembic 单一迁移链 |
| 向量库 | 课程 Milvus/其他示例 | Milvus standalone |

这不是“同时维护 MySQL 和 PostgreSQL”。课程 MySQL 只作为产品与分层思路参考；本项目不会为了兼容课程示例引入第二套主数据库，也不会复制课程配置或 SQL。

## 备选方案

### 方案 A：MySQL

优点是与课程资料接近。缺点是团队需要为复杂租户约束、JSONB 搜索和多种 partial/expression index 增加额外应用层逻辑，且与项目已固定的技术栈冲突。未采用。

### 方案 B：SQLite

适合单进程测试/演示，不适合本项目的 async 多请求、复合租户约束、生产迁移和多服务 Compose。不能作为主数据库；未来只有在保证契约一致的测试替身中才可单独评估。

### 方案 C：MongoDB

不利于统一订单/退货/支付边界的强关系、约束和事务表达，也会把结构化事实分散到文档模型。未采用。

### 方案 D：PostgreSQL + MySQL 双主库

会增加迁移、权限、备份和一致性复杂度，且没有 MVP 价值。未采用。

## 后果

正面：

- 租户/用户边界可以通过数据库约束和 Repository 双重保护。
- 订单、退款案例、退货申请、知识版本等状态机更容易做事务和并发测试。
- JSONB 与关系表可以共存，同时保留受控搜索边界。
- Docker、SQLAlchemy、Alembic 和 CI 的集成路径明确。

负面/风险：

- 团队必须维护 PostgreSQL 特定索引和迁移知识。
- JSONB 若没有白名单会变成不可控查询入口，因此 Repository 必须限制字段与操作符。
- PostgreSQL 是事实权威，但仍需 Mock OMS 的边界接口；不能把所有订单逻辑重新塞进 LLM 或缓存。
- 课程示例的 SQL/配置不能直接复用，需要独立实现和测试。

## 实施与验证

1. 阶段 4 固定 PostgreSQL 镜像版本、named volume、健康检查和 Alembic 初始化。
2. 在空库执行完整迁移，再在上一版本数据库执行增量迁移。
3. 测试复合 FK 拒绝跨店铺引用、partial unique index 阻止重复退货、金额 CHECK 拒绝负数/浮点表示。
4. 验证所有 Repository 查询都带 `shop_id` 和用户范围；不使用 `create_all()` 代替迁移。
5. 备份/恢复演练覆盖 PostgreSQL named volume 和文档原始资产。

## 合规说明

本决定不复制课程或参考项目中的数据库配置、凭据、SQL 或未核验许可证代码。任何外部实现只作为架构思路参考。
