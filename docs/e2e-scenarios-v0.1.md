# E2E Scenarios v0.1（端到端验收场景）

> 目标：用最少场景验证核心机制是否“真能跑”。

## 场景 1：正常闭环（Happy Path）

### 输入
- 一条来源可信、证据完整的 Memory（含 `evidence_refs`）

### 期望流程
1. Memory 入库
2. 生成 Experience（candidate）
3. 通过 Persona 冲突闸门
4. 生成 Cognition（supported）
5. 产出 Decision（low/medium 风险）
6. 写入 DecisionTrace 与审计事件

### 通过标准
- 全链路对象均可追溯
- 至少 1 条审计事件覆盖每次状态迁移
- DecisionTrace 字段完整且可回放

---

## 场景 2：伪造记忆注入 -> 级联回滚

### 输入
- 一条先前已参与决策的 Memory，后被确认伪造

### 期望流程
1. 注入调查触发（冻结 + 取证）
2. Memory 标记为 `rejected_poisoned`（`investigation_status=poisoned`）
3. 级联回滚 Experience/Cognition/Decision
4. 回滚事件进入审计日志

### 通过标准
- 回滚链路完整（不漏层）
- 被影响决策不可继续作为有效依据
- 回滚成功率 100%

---

## 场景 3：uncertain 到期分流

### 输入
- 一条 `epistemic_state=uncertain` 的 Cognition
- 已设置 `uncertainty_ttl`、`auto_verify_budget`

### 期望流程
1. 调度器在 `next_action_at` 到期时拉取
2. 优先执行自动验证（预算内）
3. 预算耗尽仍未解决则进入 `status=stale + epistemic_state=uncertain`
4. 对应决策模式切为保守/升级

### 通过标准
- 不出现无限挂起
- 能清晰看到“预算耗尽 -> 分流降级”的状态变化
- 高风险请求不会由 uncertain 直接驱动执行

---

## 场景 4：高风险冲动请求拦截

### 输入
- 一个高风险动作请求，当前认知为 uncertain

### 期望流程
1. 风险评估命中 `high`
2. 决策闸门拦截直接执行
3. 输出 `escalate/abstain` 并给出原因
4. 写入高风险审计轨迹

### 通过标准
- 无直接执行
- 返回结果明确包含风险、原因、下一步建议
- DecisionTrace 完整

---

## 场景 5：新证据触发 reinstate

### 输入
- 一条已降级为 `status=stale + epistemic_state=uncertain` 的 Cognition
- 新增高质量证据

### 期望流程
1. 识别新证据并进行重验证
2. 状态回升（如 `uncertain -> supported`）
3. 更新 `next_action_at/review_due_at`

### 通过标准
- 回升路径可执行、可审计
- 时间轴字段被正确重排

---

## 统一验收清单（全部场景通用）

- [ ] 每一步状态迁移都有审计事件
- [ ] 所有高风险动作都有 DecisionTrace
- [ ] `evidence_refs` 可回溯到源
- [ ] 回滚与恢复都可执行（可逆）
- [ ] 调度器仅处理到期对象（非全量扫描）

## 场景 Fixture 对应关系（可执行校验）

- 场景 1 -> `data/fixtures/critical-paths/01-happy-path.json`
- 场景 2 -> `data/fixtures/critical-paths/02-poison-rollback.json`
- 场景 3 -> `data/fixtures/critical-paths/03-uncertain-ttl-routing.json`
- 场景 4 -> `data/fixtures/critical-paths/04-high-risk-block.json`
- 场景 5 -> `data/fixtures/critical-paths/05-reinstate.json`

运行校验：`python3 tools/validate_scenarios_v0_1.py`
