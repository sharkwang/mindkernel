# State Machines v0.1（最小状态机定义）

> 目标：定义可执行、可审计、可回滚的最小状态迁移规则。

## 0. 通用约束

所有状态迁移必须满足：

1. 必须写审计事件（actor/reason/evidence_refs/before/after/timestamp）
2. 必须更新 `updated_at` 与必要的时间轴字段
3. 高风险相关迁移必须附带 `decision_trace_id`

---

## 1) Memory 状态机

### 1.1 状态集合（schema 对齐）

- `candidate`
- `quarantine`
- `verified`
- `active`
- `stale`
- `stale_uncertain`
- `rejected_poisoned`
- `archived`

### 1.2 迁移规则

| From | Trigger | To | 说明 |
|---|---|---|---|
| candidate | 初步证据校验通过 | verified | 具备最低证据门槛 |
| candidate | 注入嫌疑/来源异常 | quarantine | 进入调查隔离 |
| quarantine | 调查结论为清白 | verified | 恢复可用资格 |
| quarantine | 调查结论为伪造 | rejected_poisoned | 触发级联回滚 |
| verified | 被消费并进入链路 | active | 成为可引用证据 |
| active | 长期未访问/未强化 | stale | 时间衰减降级 |
| stale | TTL 到期且无新证据 | archived | 归档 |
| stale/stale_uncertain | 新高质量证据到达 | active | reinstate 恢复 |
| rejected_poisoned | 审计完成 | archived | 只读保留 |

### 1.3 不变量

- `rejected_poisoned` 不能直接迁回 `active`。
- `quarantine` 状态下不得参与认知升格。

---

## 2) Experience 状态机

### 2.1 状态集合（schema 对齐）

- `candidate`
- `active`
- `needs_review`
- `invalidated`
- `archived`

### 2.2 迁移规则

| From | Trigger | To | 说明 |
|---|---|---|---|
| candidate | Persona Gate 通过 + 证据充分 | active | 可用于认知抽象 |
| candidate | 证据不足/冲突待解 | needs_review | 等待复核 |
| needs_review | 新证据补齐并通过复核 | active | 恢复可用 |
| active | 上游 Memory 被判伪造 | invalidated | 级联失效 |
| needs_review/active | 到期且无价值延续 | archived | 归档 |
| invalidated | 回滚审计完成 | archived | 只读保留 |

### 2.3 不变量

- `invalidated` 不得直接转 `active`，必须创建新 Experience 或经明确 reinstate 流程。
- `needs_review` 不得直接用于高风险决策。

---

## 3) Cognition 状态机（status + epistemic_state 双轴）

### 3.1 status 轴（schema 对齐）

- `candidate`
- `active`
- `needs_revalidate`
- `stale`
- `refuted`
- `archived`

### 3.2 epistemic_state 轴

- `supported`
- `uncertain`
- `refuted`

### 3.3 关键迁移规则

| status(from) | epistemic(from) | Trigger | status(to) | epistemic(to) |
|---|---|---|---|---|
| candidate | uncertain | 通过验证 + 反例挑战通过 | active | supported |
| active | supported | 证据冲突/复核逾期 | needs_revalidate | uncertain |
| needs_revalidate | uncertain | 自动验证成功 | active | supported |
| needs_revalidate | uncertain | TTL 到期且预算耗尽 | stale | uncertain |
| active/needs_revalidate/stale | supported/uncertain | 关键反证成立 | refuted | refuted |
| stale | uncertain | 新高质量证据 | active | supported/uncertain |
| refuted | refuted | 回滚完成 | archived | refuted |

### 3.4 与 rule-table 对齐说明（术语统一）

- `rule-table-v0.1` 中的 `stale_uncertain` 在 Cognition 层对应：
  - `status = stale`
  - `epistemic_state = uncertain`
- Persona Gate 被阻断时，v0.1 采用：
  - 不创建 active cognition
  - 在 DecisionTrace 记录 `persona_conflict_gate = block`

### 3.5 不变量

- 高风险请求下，`epistemic_state=uncertain` 不得直接 `final_outcome=executed`。
- `refuted` 规则不得被新决策直接引用。

---

## 4) DecisionTrace 状态（结果约束）

DecisionTrace 不做复杂状态机，仅约束结果：

- `final_outcome ∈ {executed, limited, blocked, escalated, abstained}`
- 当 `risk_tier=high` 时，`final_outcome` 不能为 `executed`
- 当 `epistemic_state=uncertain` 时，必须含 `unknown_type`

---

## 5) 调度相关迁移触发（与 scheduler 对齐）

调度器只负责“触发”，状态机负责“落地迁移”：

1. `next_action_at` 到期 -> 进入 revalidate/verify 流程
2. `uncertainty_ttl` 到期 -> uncertain 降级或分流
3. `expires_at` 到期 -> archive/freeze
4. 新证据事件 -> reinstate 候选迁移

> 详细接口见 `docs/02-design/scheduler-interface-v0.1.md`。
