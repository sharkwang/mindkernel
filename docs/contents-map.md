# Contents Map (v10)

本文件用于整理 `mindkernel/docs` 文档结构，避免信息分散。

## 核心规范（优先阅读）

1. `01-foundation/requirements-and-architecture.md`
   - 主规范（MR/CR/FR/NFR、V&V、Traceability、Open Issues）
2. `01-foundation/project-charter.md`
   - 项目宪法级方向与阶段目标

## 讨论与追溯

3. `05-history/discussion-log.md`
   - 关键讨论与决策时间线
4. `05-history/name-origin.md`
   - 命名来源与更名说明

## v0.1 启动包（当前执行主线）

5. `01-foundation/mindkernel-v0.1-scope.md`
   - v0.1 交付边界、里程碑、Go/No-Go
6. `02-design/rule-table-v0.1.md`
   - 可执行规则表（IF/THEN）
7. `02-design/state-machines-v0.1.md`
   - Memory / Experience / Cognition 最小状态机
8. `02-design/scheduler-interface-v0.1.md`
   - `next_action_at` 到期调度接口草案
9. `03-validation/e2e-scenarios-v0.1.md`
   - 端到端验收场景
10. `02-design/rtm-v0.1.md`
   - v0.1 需求追踪子表（覆盖主规范条款）
11. `02-design/design-consolidation-v0.1.md`
   - docs + schemas 统一口径与术语整理基线
12. `03-validation/validation-critical-paths-v0.1.md`
   - v0.1 fixtures + 校验脚本的关键路径覆盖说明
13. `04-prototypes/scheduler-prototype-v0.1.md`
   - 调度器接口的本地可运行原型说明
14. `04-prototypes/memory-experience-prototype-v0.1.md`
   - 记忆到经验路径的本地可运行原型说明
15. `04-prototypes/experience-cognition-prototype-v0.1.md`
   - 经验到认知路径（含 Persona Gate 最小实现）
16. `04-prototypes/cognition-decision-prototype-v0.1.md`
   - Cognition→DecisionTrace 最小链路说明
17. `04-prototypes/full-path-prototype-v0.1.md`
   - Memory→Experience→Cognition→Decision 一体化最小闭环说明
18. `03-validation/system-smoke-report-v0.1.md`
   - 系统烟测报告产出与解读方式

## 数据契约草案（与主规范配套）

19. `../schemas/README.md`
    - schema 草案索引与维护说明
20. `../schemas/*.schema.json`
    - `common-temporal` / `persona` / `memory` / `experience` / `cognition` / `decision-trace` / `audit-event`

## 归档文档（只读）

21. `../archive/requirements-and-architecture.legacy.md`
22. `../archive/design.legacy.md`
23. `../archive/memory-entry.schema.legacy.json`

## 维护规则

- 新决策：先写入 `discussion-log`，达成共识后再写入主规范。
- v0.1 改动：同步更新 `02-design/rtm-v0.1.md` 与 `03-validation/e2e-scenarios-v0.1.md`。
- 归档目录只读，不再追加新条款。
