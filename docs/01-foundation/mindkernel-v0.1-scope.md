# MindKernel v0.1 Scope（启动范围）

> 目标：先跑通最小可验证闭环，不追求一次做全。

## 1. v0.1 一句话目标

在单用户、单节点环境下，稳定跑通：

`Memory -> Experience -> Cognition -> Decision -> Feedback`

并满足最小可审计、可回滚、可解释要求。

## 2. In-Scope（本期必须交付）

1. **四层对象最小模型**
   - Memory / Experience / Cognition / DecisionTrace
2. **认知三态机制**
   - `supported / uncertain / refuted`
3. **风险分层决策**
   - `low / medium / high`
4. **未知态分流（仅最小实现）**
   - `multipath / out_of_scope / ontic_unknowable`
5. **时间轴驱动调度（最小版）**
   - 基于 `next_action_at` 拉取到期对象
6. **最小审计链**
   - 全量记录关键状态变更与依据
7. **级联回滚（最小可用）**
   - 从伪造/失效 Memory 触发向上游影响对象回滚

## 3. Out-of-Scope（本期明确不做）

1. 多租户/多用户隔离治理
2. 复杂 UI 工作台（先 CLI/脚本化）
3. 大规模分布式调度与高可用
4. 自动化模型训练与在线学习平台
5. 跨项目知识共享网络
6. 高级推理图谱（Graph Reasoning）

## 4. v0.1 交付物清单

- 文档
  - `docs/02-design/rule-table-v0.1.md`
  - `docs/03-validation/e2e-scenarios-v0.1.md`
  - `docs/01-foundation/mindkernel-v0.1-scope.md`（本文档）
- 数据契约
  - `schemas/decision-trace.schema.json`
  - `schemas/audit-event.schema.json`
- 运行能力（最小）
  - 对象创建与状态变更
  - 到期调度任务执行
  - 审计追踪写入
  - 级联回滚演示

## 5. 里程碑（建议 10 个工作日）

- **M1（D1-D2）**：规则冻结（状态机 + 决策表）
- **M2（D3-D5）**：最小执行链路打通
- **M3（D6-D7）**：调度器 + 时间轴动作联调
- **M4（D8-D9）**：E2E 场景验收（含回滚）
- **M5（D10）**：v0.1 冻结与复盘

## 6. 验收门槛（Go/No-Go）

1. 至少 3 条端到端场景全部通过（见 `03-validation/e2e-scenarios-v0.1.md`）
2. 高风险决策 100% 具备 DecisionTrace
3. 注入场景回滚成功率 = 100%
4. `uncertain` 到期事项可自动分流，不出现无限悬挂

## 7. 风险与对应缓解

- 风险：规则定义不清，导致实现漂移
  - 缓解：先冻结 `02-design/rule-table-v0.1.md`，再写实现
- 风险：审计后补，导致链路断裂
  - 缓解：把审计写入作为“默认路径”而非可选项
- 风险：调度器复杂度提前膨胀
  - 缓解：v0.1 仅实现单队列到期拉取

## 8. 本期默认工程约束

- 单时区统一使用 ISO-8601（UTC 存储）
- 所有状态迁移必须带 `reason` + `evidence_refs`
- 任何高风险动作必须产出 `decision_mode` 与 `risk_tier`
- 不允许“静默改写”认知状态（必须有事件记录）
