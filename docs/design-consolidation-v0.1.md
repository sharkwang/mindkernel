# Design Consolidation v0.1（设计整理基线）

> 本文档是对当前 docs + schemas 的一次“统一口径整理”，用于降低术语漂移与实现歧义。

## 1) 统一口径（Canonical）

### 1.1 认知降级术语

- 概念层可以使用 `stale_uncertain`。
- 实体层（Cognition）统一表达为：
  - `status = stale`
  - `epistemic_state = uncertain`

### 1.2 注入判定术语

- Memory 注入确认后统一状态：`status = rejected_poisoned`
- 调查字段：`investigation_status = poisoned`
- 不再使用 `forged/invalidated` 作为 Memory 的正式状态枚举。

### 1.3 Persona Gate 阻断语义

- 阻断是“闸门结果”，不是 Cognition 的状态枚举。
- 统一记录方式：
  - 不进入 `cognition.status=active`
  - 在 DecisionTrace 记录 `persona_conflict_gate=block`

## 2) 当前对象与职责边界

- `memory.schema.json`：证据对象（来源、可信度、风险、调查与衰减因子）
- `experience.schema.json`：事件化/结果化经验对象（连接 Memory 与 Cognition）
- `cognition.schema.json`：规则对象（三态认知、未知态、决策模式）
- `decision-trace.schema.json`：决策审计对象（闸门、依据、结论）
- `audit-event.schema.json`：审计事件对象（状态迁移、回滚、调度治理事件）
- `common-temporal.schema.json`：统一时间轴字段

## 3) v0.1 执行链路（实现优先级）

1. **状态机先行**：按 `state-machines-v0.1.md` 落地迁移函数。
2. **调度触发**：按 `scheduler-interface-v0.1.md` 落地到期拉取与重试。
3. **审计闭环**：每次迁移写审计，所有高风险决策写 DecisionTrace。
4. **E2E 验收**：按 `e2e-scenarios-v0.1.md` 跑 5 个场景。

## 4) 本轮整理后的一致性结果

- 已对齐：
  - Rule Table 与状态机术语（`needs_review`、gate=block）
  - E2E 场景与 schema 状态枚举（`rejected_poisoned`）
  - Schema 索引包含 `decision-trace` 与 `audit-event`
- 已补强：
  - Memory 增加 `evidence_refs` 必填约束（与规则一致）
  - 新增独立 `audit-event.schema.json`（承接状态迁移与治理动作审计）

## 5) 仍保留的设计张力（下轮处理）

1. `common-temporal` 对 Persona 的字段强制程度是否过高。
2. `CR/FR` 中概念词（如 `stale_uncertain`）与数据层枚举如何长期治理。
3. `audit-event` 与 `decision-trace` 的边界（事件流 vs 决策快照）还需在实现层进一步固化。

## 6) 维护规则

- 先改规则，再改 schema，再改 E2E。
- 任一术语变更必须同步更新：
  - `rule-table-v0.1.md`
  - `state-machines-v0.1.md`
  - `e2e-scenarios-v0.1.md`
  - 对应 schema
