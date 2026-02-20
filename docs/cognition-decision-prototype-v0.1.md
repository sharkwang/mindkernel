# Cognition-Decision Prototype v0.1（闭环最后一跳）

> 目标：实现 `Cognition -> DecisionTrace` 的最小可执行链路，完成 M→E→C→D 闭环关键拼图。

## 1. 实现位置

- 脚本：`tools/cognition_decision_v0_1.py`
- 存储：`data/mindkernel_v0_1.sqlite`

## 2. 支持命令

- `init-db`
- `ingest-cognition`
- `cognition-to-decision`
- `run-path`
- `list-cognition`
- `list-decisions`
- `list-audits`

## 3. 最小决策策略

- 输入：Cognition 对象（含 `epistemic_state` 与风险字段）
- 核心分流：
  - `supported + low/medium risk` -> `decision_mode=normal`, `final_outcome=executed`
  - `supported + high risk` -> 保守限域（`final_outcome=limited`）
  - `uncertain + medium risk` -> `conservative`, `limited`
  - `uncertain + high risk` -> `escalate`, `escalated`
  - `refuted` -> `abstain`, `abstained`
- 输出：`decision-trace.schema.json` 合法对象 + `decision_gate` 审计事件

## 4. 快速跑通

### 4.1 Pass 路径（supported）

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/cognition_decision_v0_1.py init-db
python3 tools/cognition_decision_v0_1.py run-path \
  --file data/fixtures/critical-paths/14-cognition-decision-pass.json \
  --request-ref req://demo/pass
```

### 4.2 High-risk 路径（uncertain）

```bash
python3 tools/cognition_decision_v0_1.py run-path \
  --file data/fixtures/critical-paths/15-cognition-decision-high-risk-block.json \
  --request-ref req://demo/high-risk
```

## 5. 设计对齐

- Cognition 入库前执行 `cognition.schema.json` 校验
- Decision 输出前执行 `decision-trace.schema.json` 校验
- 审计事件写入前执行 `audit-event.schema.json` 校验
