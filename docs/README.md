# ShopMate 文档索引

> 阶段 14 整理。文档按“为什么做 → 怎么设计 → 怎么实现 → 怎么验证 → 怎么部署”排序。
> 契约类文档（03/04/05/06/07）是实现的依据；`project-status.md` 是各阶段的事实记录。

## 1. 产品与决策

| 文档 | 内容 | 阶段 |
|---|---|---|
| [`00-course-distillation.md`](00-course-distillation.md) | 课程资料提炼与不照搬项 | 1 |
| [`01-audit.md`](01-audit.md) | 只读审计、风险清单 | 1 |
| [`01-github-research.md`](01-github-research.md) | 参考仓库与许可证核验 | 1 |
| [`02-prd.md`](02-prd.md) | 用户故事、MVP、验收标准、非目标 | 2 |
| [`adr/`](adr/) | 架构决策记录（数据库、检索、SSE 等） | 3 |

## 2. 契约与设计

| 文档 | 内容 |
|---|---|
| [`03-architecture.md`](03-architecture.md) | 组件图、请求时序、三条核心路径、降级策略 |
| [`04-data-contract.md`](04-data-contract.md) | 表结构、字段、索引、状态机、多租户约束 |
| [`05-tool-contract.md`](05-tool-contract.md) | 工具清单、输入输出信封、错误码、幂等 |
| [`06-api.md`](06-api.md) | REST + SSE 契约、错误码、实现现状勘误 |
| [`07-security.md`](07-security.md) | 威胁模型、PII、护栏、发布安全门禁、阶段 14 复查 |

## 3. 实现与验收

| 文档 | 内容 |
|---|---|
| [`test-report.md`](test-report.md) | 单元/集成/E2E/安全测试与故障演练 |
| [`eval-report.md`](eval-report.md) | 评测集、RAG 指标、业务指标、压测、失败案例 |
| [`project-status.md`](project-status.md) | 各阶段实施、整改与验收记录（含 §22 阶段 14） |

## 4. 运维与演示

| 文档 | 内容 |
|---|---|
| [`08-deployment.md`](08-deployment.md) | 生产拓扑、部署步骤、迁移、备份/恢复、安全复查、故障处理 |
| [`09-release-checklist.md`](09-release-checklist.md) | 全新环境启动与发布检查清单（可勾选） |
| [`demo.md`](demo.md) | 3 分钟 / 10 分钟演示脚本与证据清单 |
| [`resume-evidence.md`](resume-evidence.md) | 可复现的工程证据台账：指标证据表、实现状态三分、缺陷定位（阶段 15） |
| [`interview-prep.md`](interview-prep.md) | 中文简历项目描述 + 15 个面试问答提纲 + 数字速查卡（阶段 15） |

## 5. 阅读顺序建议

- **新同学**：README → 03-architecture → 06-api → 08-deployment。
- **评审**：02-prd → 07-security → test-report → eval-report。
- **演示**：demo.md → 09-release-checklist。
