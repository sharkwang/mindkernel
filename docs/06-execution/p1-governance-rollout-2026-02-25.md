# P1/P2 收口执行单（2026-02-25）

> 目标：一次性推进并落地三项剩余主线：
> 1) 真实 workspace 回放；2) 多 worker 锁机制；3) 遗忘执行层 worker 化。

## 1. 执行计划

### A. 真实 workspace 回放（非 fixture）
- [x] 新增 `tools/validation/validate_scheduler_workspace_replay_v0_1.py`
- [x] 使用真实仓库路径作为 workspace，临时 DB/index/reports 回放
- [x] 覆盖失败恢复路径：故意 bad gate config -> retry -> second run recover
- [x] 输出可审计 JSON 结果（处理量、恢复情况、产物路径）

### B. 多 worker 租约/锁机制
- [x] 在 `scheduler_jobs` 增加 `lease_token`、`lease_expires_at`
- [x] `pull_due` 增加 `BEGIN IMMEDIATE + 条件领取 + action filter`
- [x] 增加 lease 过期回收（running -> queued）
- [x] `ack/fail` 增加 worker/lease 校验，避免过期 worker 越权提交
- [x] 新增验证：`validate_scheduler_multi_worker_lock_v0_1.py`

### C. 遗忘执行层补齐（decay/archive/reinstate-check）
- [x] 新增 `tools/scheduler/temporal_governance_worker_v0_1.py`
- [x] 支持对象：`memory_items`、`experience_records`
- [x] 支持动作：`decay`、`archive`、`reinstate-check`
- [x] 每次迁移写 `AuditEvent(state_transition)` + 调度 ack/fail 审计
- [x] 新增验证：`validate_temporal_governance_worker_v0_1.py`

## 2. 门禁联动更新

- [x] `tools/release/release_check_v0_1.py` 增补检查项：
  - `validate-scheduler-multi-worker-lock`
  - `validate-temporal-governance-worker`
  - `validate-workspace-replay`

## 3. 证据路径

- 核心代码：
  - `tools/scheduler/scheduler_v0_1.py`
  - `tools/scheduler/reflect_scheduler_worker_v0_1.py`
  - `tools/scheduler/temporal_governance_worker_v0_1.py`
- 验证脚本：
  - `tools/validation/validate_scheduler_multi_worker_lock_v0_1.py`
  - `tools/validation/validate_temporal_governance_worker_v0_1.py`
  - `tools/validation/validate_scheduler_workspace_replay_v0_1.py`
- 文档同步：
  - `docs/04-prototypes/scheduler-prototype-v0.1.md`
  - `tools/README.md`
  - `tools/validation/README.md`
  - `test/README.md`

## 4. 风险与后续

- 当前仍为单库 SQLite 架构；lease 机制解决领取冲突，但不等于分布式调度。
- long-running 任务尚未支持 lease 心跳续约（后续可加 renew API）。
- temporal worker 已覆盖 FR-20/FR-21 的最小执行层，后续补 verify/revalidate 统一执行器。