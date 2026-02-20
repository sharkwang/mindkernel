# Rule Table v0.1（可执行规则表）

> 目的：先把“怎么判定”写清楚，再进入实现。

## 1. Memory -> Experience

| Rule ID | 条件（IF） | 动作（THEN） | 输出状态 |
|---|---|---|---|
| R-ME-01 | Memory 新建且 `evidence_refs >=1` | 创建 Experience 候选 | `experience.status = candidate` |
| R-ME-02 | Memory 来源可信度低且存在冲突证据 | 标记为待核验，不允许升格 | `experience.status = needs_verify` |
| R-ME-03 | Memory 被判定伪造 | 触发级联回滚流程 | `experience.status = invalidated` |

## 2. Experience -> Cognition

| Rule ID | 条件（IF） | 动作（THEN） | 输出状态 |
|---|---|---|---|
| R-EC-01 | Experience 通过 Persona 冲突闸门 + 最低证据门槛 | 生成 Cognition 候选 | `cognition.status = candidate` |
| R-EC-02 | 与 Persona 硬边界冲突 | 禁止升格 + 记录冲突 | `cognition.status = blocked` |
| R-EC-03 | 证据不足但具潜在价值 | 进入 uncertain 并分配 TTL | `epistemic_state = uncertain` |

## 3. Cognition 三态迁移

| Rule ID | 条件（IF） | 动作（THEN） | 新状态 |
|---|---|---|---|
| R-CG-01 | 通过反例挑战且证据一致性达标 | 发布可用规则 | `supported` |
| R-CG-02 | 证据冲突或时效到期未复核 | 降级并限制决策模式 | `uncertain` |
| R-CG-03 | 关键反证成立 | 立即下线并触发影响分析 | `refuted` |

## 4. uncertain 分流（风险 × 未知态）

| Rule ID | 条件（IF） | 动作（THEN） | 决策模式 |
|---|---|---|---|
| R-UN-01 | `risk=low` + `unknown_type=multipath` | 保留多假设并可探索执行 | `explore` |
| R-UN-02 | `risk=medium` + 任意未知态 | 限域执行 + 降权限 | `conservative` |
| R-UN-03 | `risk=high` + 任意未知态 | 禁止直接执行，转升级或拒绝 | `escalate/abstain` |
| R-UN-04 | `unknown_type=out_of_scope` 且预算未耗尽 | 自动调用补证流程 | `auto_verify` |
| R-UN-05 | `unknown_type=ontic_unknowable` | 停止重复强验证，明确不可知边界 | `value-bounded action` |

## 5. 时间轴调度规则（next_action_at）

| Rule ID | 条件（IF） | 动作（THEN） |
|---|---|---|
| R-TM-01 | `now >= next_action_at` 且对象为 uncertain | 触发复核或自动验证 |
| R-TM-02 | `uncertainty_ttl` 到期且预算耗尽 | 标记 `stale_uncertain` 并降权 |
| R-TM-03 | `expires_at` 到期 | 归档或冻结（按风险层） |
| R-TM-04 | 有新高质量证据到达 | 允许 reinstate 并重排 `next_action_at` |

## 6. 级联回滚规则

| Rule ID | 触发条件 | 回滚范围 | 结果 |
|---|---|---|---|
| R-RB-01 | Memory 判定伪造 | Memory -> Experience -> Cognition -> DecisionTrace | 影响链全部标记 `invalidated` |
| R-RB-02 | Cognition 被 refuted | 依赖该规则的决策结果 | 决策降级/撤销并重评估 |

## 7. 审计规则（必须）

| Rule ID | 要求 |
|---|---|
| R-AU-01 | 每次状态迁移都必须写入 audit 事件 |
| R-AU-02 | audit 事件必须包含：actor、reason、evidence_refs、before、after、timestamp |
| R-AU-03 | 高风险决策必须绑定 `decision_trace_id` |

## 8. v0.1 默认阈值（可调）

- 最低证据数：`min_evidence_count = 1`
- uncertain 默认 TTL：`P7D`
- auto verify 预算：`2`
- 高风险阈值：`risk_tier = high`（直接禁止 uncertain 直出）

> 注：以上阈值仅作为 v0.1 启动参数，后续由治理作业调优。
