# Scheduler Prototype v0.1（最小可运行原型）

> 目标：把 `02-design/scheduler-interface-v0.1.md` 从接口草案推进到本地可运行脚本。

## 1. 实现位置

- 脚本：`tools/scheduler/scheduler_v0_1.py`
- worker：`tools/scheduler/reflect_scheduler_worker_v0_1.py`、`tools/scheduler/temporal_governance_worker_v0_1.py`
- 核心闸门模块：`core/reflect_gate_v0_1.py`
- 存储：`data/mindkernel_v0_1.sqlite`（运行时生成）

## 2. 支持命令

- `init-db`
- `enqueue`
- `pull`
- `ack`
- `fail`
- `stats`
- `list-audits`
- `route-proposals`（Agent-first 风险分流：auto_apply / sample_review / mandatory_review）

## 3. 快速开始

```bash
cd /Users/zhengwang/projects/mindkernel

# 1) 初始化数据库
python3 tools/scheduler/scheduler_v0_1.py init-db

# 2) 入队一个到期任务
python3 tools/scheduler/scheduler_v0_1.py enqueue \
  --object-type cognition \
  --object-id cg_demo_001 \
  --action revalidate \
  --run-at 2026-02-20T12:00:00Z \
  --priority high

# 3) 拉取到期任务（会标记 running，并分配 lease）
python3 tools/scheduler/scheduler_v0_1.py pull \
  --worker-id worker-1 \
  --now 2026-02-20T12:01:00Z \
  --limit 10 \
  --lease-sec 120

# 4) 成功确认
python3 tools/scheduler/scheduler_v0_1.py ack --job-id <job_id>

# 5) 查看统计
python3 tools/scheduler/scheduler_v0_1.py stats

# 6) 查看最近审计事件
python3 tools/scheduler/scheduler_v0_1.py list-audits --limit 10

# 7) Agent-first 提案分流（machine-readable 输出）
python3 tools/scheduler/scheduler_v0_1.py route-proposals \
  --input data/reflect_proposals_demo.json \
  --output reports/reflect_proposals_routed_demo.json

# 8) 高风险人格冲突入确认队列（异步人审）
python3 tools/scheduler/persona_confirmation_queue_v0_1.py \
  --db data/mindkernel_v0_1.sqlite \
  enqueue-from-routed \
  --routed-file reports/reflect_proposals_routed_demo.json

# 9) 生成 reflect apply 计划（仅 auto_applied + human approved）
python3 tools/scheduler/persona_confirmation_queue_v0_1.py \
  --db data/mindkernel_v0_1.sqlite \
  apply-plan \
  --routed-file reports/reflect_proposals_routed_demo.json \
  --apply-out reports/reflect_apply_candidates_demo.jsonl \
  --blocked-out reports/reflect_apply_blocked_demo.jsonl \
  --output reports/reflect_apply_plan_demo.json

# 10) 执行 apply 写回（带幂等账本 + DecisionTrace/AuditEvent）
python3 tools/scheduler/persona_confirmation_queue_v0_1.py \
  --db data/mindkernel_v0_1.sqlite \
  apply-exec \
  --plan-file reports/reflect_apply_plan_demo.json \
  --workspace /Users/zhengwang/projects/mindkernel \
  --output reports/reflect_apply_exec_demo.json

# 10.1) 查看/处理补偿队列（C4）
python3 tools/scheduler/persona_confirmation_queue_v0_1.py --db data/mindkernel_v0_1.sqlite compensations --status pending
python3 tools/scheduler/persona_confirmation_queue_v0_1.py --db data/mindkernel_v0_1.sqlite resolve-compensation --compensation-id <id> --note "manual handled"

# 11) worker loop（S7，默认 dry-run）
python3 tools/scheduler/reflect_scheduler_worker_v0_1.py \
  --db data/mindkernel_v0_1.sqlite \
  --workspace /Users/zhengwang/projects/mindkernel \
  --memory-index-db .memory/index.sqlite \
  --reports-dir reports/reflect_scheduler \
  --lease-sec 120 \
  --run-once

# 12) 遗忘执行层 worker（decay/archive/reinstate-check）
python3 tools/scheduler/temporal_governance_worker_v0_1.py \
  --db data/mindkernel_v0_1.sqlite \
  --lease-sec 120 \
  --run-once
```

## 4. 对齐点（与设计文档）

- 到期拉取：按 `run_at <= now`
- 排序策略：`run_at ASC` + `priority DESC`
- 幂等：`idempotency_key` 去重
- 重试：`fail` 后按 `retry_delay_sec` 重新入队
- 死信：超过 `max_attempts` -> `dead_letter`
- 租约锁：`pull` 领取任务时分配 `lease_token + lease_expires_at`，过期任务自动回收重排
- 动作过滤：`pull` 支持 action 过滤（reflect/decay/archive/reinstate-check）
- 审计：enqueue/pull/ack/fail 自动写 `audit_events`（`event_type=scheduler_job`）
- Agent-first 闸门：`route-proposals` 按 `risk_score + hard_rules` 分流（low 自动、medium 抽检、high 必审）

## 5. 当前边界（v0.1）

- 单实例 SQLite
- 已支持多 worker 领取租约与过期回收（仍建议先单库部署）
- reflect 与 temporal worker 分离执行（action filter），避免跨类型误处理
- `audit_events` 记录调度动作 + temporal 状态迁移，不替代完整业务审计

## 6. 下一步建议

1. 为 lease 增加心跳续约（long-running 作业）与 worker 崩溃探测
2. 扩展 temporal 执行器到 `verify/revalidate`（当前覆盖 `decay/archive/reinstate-check`）
3. 增加调度回放中的失败补偿与回滚演练（含 dead_letter）
