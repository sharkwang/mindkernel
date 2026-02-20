# Contents Map (v4)

本文件用于整理 `mindkernel/docs` 文档结构，避免信息分散。

## 核心规范（优先阅读）

1. `requirements-and-architecture.md`
   - 主规范（MR/CR/FR/NFR、V&V、Traceability、Open Issues）
2. `project-charter.md`
   - 项目宪法级方向与阶段目标

## 讨论与追溯

3. `discussion-log.md`
   - 关键讨论与决策时间线
4. `name-origin.md`
   - 命名来源与更名说明

## v0.1 启动包（当前执行主线）

5. `mindkernel-v0.1-scope.md`
   - v0.1 交付边界、里程碑、Go/No-Go
6. `rule-table-v0.1.md`
   - 可执行规则表（IF/THEN）
7. `state-machines-v0.1.md`
   - Memory / Experience / Cognition 最小状态机
8. `scheduler-interface-v0.1.md`
   - `next_action_at` 到期调度接口草案
9. `e2e-scenarios-v0.1.md`
   - 端到端验收场景
10. `rtm-v0.1.md`
   - v0.1 需求追踪子表（覆盖主规范条款）
11. `design-consolidation-v0.1.md`
   - docs + schemas 统一口径与术语整理基线
12. `validation-critical-paths-v0.1.md`
   - v0.1 fixtures + 校验脚本的关键路径覆盖说明

## 数据契约草案（与主规范配套）

13. `../schemas/README.md`
    - schema 草案索引与维护说明
14. `../schemas/*.schema.json`
    - `common-temporal` / `persona` / `memory` / `experience` / `cognition` / `decision-trace` / `audit-event`

## 归档文档（只读）

15. `../archive/requirements-and-architecture.legacy.md`
16. `../archive/design.legacy.md`
17. `../archive/memory-entry.schema.legacy.json`

## 维护规则

- 新决策：先写入 `discussion-log`，达成共识后再写入主规范。
- v0.1 改动：同步更新 `rtm-v0.1.md` 与 `e2e-scenarios-v0.1.md`。
- 归档目录只读，不再追加新条款。
