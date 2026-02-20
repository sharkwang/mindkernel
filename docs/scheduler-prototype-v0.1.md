# Scheduler Prototype v0.1（最小可运行原型）

> 目标：把 `scheduler-interface-v0.1.md` 从接口草案推进到本地可运行脚本。

## 1. 实现位置

- 脚本：`tools/scheduler_v0_1.py`
- 存储：`data/mindkernel_v0_1.sqlite`（运行时生成）

## 2. 支持命令

- `init-db`
- `enqueue`
- `pull`
- `ack`
- `fail`
- `stats`

## 3. 快速开始

```bash
cd /Users/zhengwang/projects/mindkernel

# 1) 初始化数据库
python3 tools/scheduler_v0_1.py init-db

# 2) 入队一个到期任务
python3 tools/scheduler_v0_1.py enqueue \
  --object-type cognition \
  --object-id cg_demo_001 \
  --action revalidate \
  --run-at 2026-02-20T12:00:00Z \
  --priority high

# 3) 拉取到期任务（会标记 running）
python3 tools/scheduler_v0_1.py pull --worker-id worker-1 --now 2026-02-20T12:01:00Z --limit 10

# 4) 成功确认
python3 tools/scheduler_v0_1.py ack --job-id <job_id>

# 5) 查看统计
python3 tools/scheduler_v0_1.py stats
```

## 4. 对齐点（与设计文档）

- 到期拉取：按 `run_at <= now`
- 排序策略：`run_at ASC` + `priority DESC`
- 幂等：`idempotency_key` 去重
- 重试：`fail` 后按 `retry_delay_sec` 重新入队
- 死信：超过 `max_attempts` -> `dead_letter`

## 5. 当前边界（v0.1）

- 单实例 SQLite
- 单 worker 友好（多 worker 竞争需后续补事务锁策略）
- 只做任务调度，不直接改业务对象状态

## 6. 下一步建议

1. 增加 `worker loop`（定时 pull + 处理 + ack/fail）
2. 接入 `audit-event` 写入（scheduler_job 事件）
3. 增加与 fixtures 联动的调度回放测试
