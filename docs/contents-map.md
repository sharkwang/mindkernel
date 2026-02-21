# Contents Map (v12)

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
9. `02-design/rtm-v0.1.md`
   - v0.1 需求追踪子表（覆盖主规范条款）
10. `02-design/design-consolidation-v0.1.md`
    - docs + schemas 统一口径与术语整理基线
11. `02-design/memory-index-architecture-v0.1.md`
    - Markdown 规范源 + 派生索引架构草案
12. `02-design/retain-recall-reflect-spec-v0.1.md`
    - retain/recall/reflect 语法与接口规范草案
13. `03-validation/e2e-scenarios-v0.1.md`
    - 端到端验收场景
14. `03-validation/validation-critical-paths-v0.1.md`
    - v0.1 fixtures + 校验脚本的关键路径覆盖说明
15. `03-validation/system-smoke-report-v0.1.md`
    - 系统烟测报告产出与解读方式
16. `04-prototypes/memory-index-prototype-v0.1.md`
    - retain/recall/reflect 索引原型说明
17. `04-prototypes/scheduler-prototype-v0.1.md`
    - 调度器接口的本地可运行原型说明
18. `04-prototypes/memory-experience-prototype-v0.1.md`
    - 记忆到经验路径的本地可运行原型说明
19. `04-prototypes/experience-cognition-prototype-v0.1.md`
    - 经验到认知路径（含 Persona Gate 最小实现）
20. `04-prototypes/cognition-decision-prototype-v0.1.md`
    - Cognition→DecisionTrace 最小链路说明
21. `04-prototypes/full-path-prototype-v0.1.md`
    - Memory→Experience→Cognition→Decision 一体化最小闭环说明

## 数据契约草案（与主规范配套）

22. `../schemas/README.md`
    - schema 草案索引与维护说明
23. `../schemas/*.schema.json`
    - `common-temporal` / `persona` / `memory` / `experience` / `cognition` / `decision-trace` / `audit-event`

## 归档文档（只读）

24. `../archive/requirements-and-architecture.legacy.md`
25. `../archive/design.legacy.md`
26. `../archive/memory-entry.schema.legacy.json`

## 执行计划

27. `06-execution/v0.1.0-usable-execution-plan.md`
    - v0.1.0-usable 从原型到可交付版本的执行规划（S1~S11）

## 维护规则

- 新决策：先写入 `05-history/discussion-log.md`，达成共识后再写入主规范。
- v0.1 改动：同步更新 `02-design/rtm-v0.1.md` 与 `03-validation/e2e-scenarios-v0.1.md`。
- 归档目录只读，不再追加新条款。
