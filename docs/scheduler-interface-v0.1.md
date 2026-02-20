# Scheduler Interface v0.1（next_action_at 调度器接口草案）

> 目标：以最小接口支持“到期驱动”治理，避免默认全量扫描。

## 1. 设计边界

- v0.1 范围：单实例、单队列、按到期拉取
- 触发对象：Memory / Experience / Cognition
- 触发动作：verify / revalidate / decay / archive / reinstate-check

## 2. 核心对象

```json
{
  "job_id": "job_xxx",
  "object_type": "memory|experience|cognition",
  "object_id": "...",
  "action": "verify|revalidate|decay|archive|reinstate-check",
  "run_at": "2026-02-20T03:00:00Z",
  "priority": "low|medium|high",
  "attempt": 0,
  "max_attempts": 3,
  "idempotency_key": "object_id:action:run_at",
  "status": "queued|running|succeeded|failed|dead_letter",
  "last_error": null
}
```

## 3. 接口定义（逻辑 API）

### 3.1 Enqueue（写入任务）

`POST /scheduler/jobs`

请求示例：

```json
{
  "object_type": "cognition",
  "object_id": "cg_123",
  "action": "revalidate",
  "run_at": "2026-02-21T00:00:00Z",
  "priority": "medium"
}
```

约束：
- 同一 `idempotency_key` 不重复入队
- `run_at` 必须 >= 当前时间

---

### 3.2 Pull Due Jobs（拉取到期任务）

`POST /scheduler/jobs/pull`

请求示例：

```json
{
  "now": "2026-02-21T00:00:10Z",
  "limit": 100,
  "worker_id": "worker-1"
}
```

返回：按 `run_at asc, priority desc` 返回 `queued` 任务并置为 `running`。

---

### 3.3 Ack（执行完成）

`POST /scheduler/jobs/{job_id}/ack`

请求示例：

```json
{
  "result": "succeeded",
  "audit_event_id": "aud_789",
  "next_action_at": "2026-02-28T00:00:00Z"
}
```

行为：
- 置 `status=succeeded`
- 将 `next_action_at` 回写对象
- 写审计事件关联

---

### 3.4 Fail/Retry（失败与重试）

`POST /scheduler/jobs/{job_id}/fail`

请求示例：

```json
{
  "error": "timeout while verifying evidence",
  "retry_delay_sec": 300
}
```

行为：
- `attempt + 1`
- 若 `attempt < max_attempts`：重新入队，`run_at += retry_delay_sec`
- 否则进入 `dead_letter` 并触发告警事件

## 4. 调度策略

1. **到期优先**：只处理 `run_at <= now` 的任务
2. **优先级加权**：`high > medium > low`
3. **幂等执行**：同一 `idempotency_key` 不重复副作用
4. **失败隔离**：超重试上限进入 `dead_letter`，不阻塞主队列

## 5. 与状态机的责任边界

- 调度器负责：任务时机与重试
- 状态机负责：状态合法性与迁移
- 审计器负责：记录 before/after 与证据

## 6. 最小实现建议（v0.1）

- 存储：SQLite 单表（jobs）+ 索引 `(status, run_at)`
- worker：单进程循环（固定 interval，例如 5s）
- 回写：通过统一 service 层调用状态机迁移函数

## 7. 可观测性指标（v0.1）

- `jobs_due_count`
- `jobs_lag_seconds`（当前时间 - 最早到期未执行时间）
- `job_success_rate`
- `job_retry_rate`
- `dead_letter_count`

## 8. 安全与治理约束

1. 高风险对象任务执行前必须读取最新 Persona/Cognition 门禁状态
2. `uncertain` 的自动验证不得突破 `auto_verify_budget`
3. `ontic_unknowable` 禁止无限重试验证（必须有上限退出）

## 9. 开放项（v0.2）

- 多队列分片（按对象类型/风险层）
- 优先队列或时间轮优化
- 分布式 worker 锁与租约机制
- 调度/执行分离的事件总线化
