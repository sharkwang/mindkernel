# MindKernel v0.2 Daemon Runbook（D5/D6）

_日期：2026-03-03_

## 0. 目的
本 runbook 定义 v0.2 daemon 的运行策略、灰度路径与回退机制，保证“默认安全、可逐步放量、可一键回退”。

---

## 1. 运行策略（Feature Flag）

daemon 参数：`--feature-flag off|shadow|partial|on`（默认 `off`）

- `off`：只做观测，不提炼入队（最安全）
- `shadow`：做 normalize/dedupe/candidate，但不 enqueue（影子模式）
- `partial`：仅 allowlist session 入队（灰度）
- `on`：全量入队（生产）

可选参数：
- `--partial-session-allowlist <file>`：partial 模式会话白名单
- `--scheduler-db <path>`：入队目标
- `--enqueue-min-risk-level low|medium|high`

---

## 2. 推荐灰度路径

1. **dev/off**：先验证稳定性（无入队副作用）
2. **shadow**：验证候选质量、重复率、节流效果
3. **partial**：仅放行目标会话
4. **on**：全量放开（仍保留风险分层与高水位保护）

---

## 3. 一键回退（Batch-only）

控制脚本：`scripts/daemon_v0_2_control.sh`

- 启动（示例）
  - `./scripts/daemon_v0_2_control.sh start-shadow`
  - `./scripts/daemon_v0_2_control.sh start-partial data/daemon/partial_sessions.allowlist`
  - `./scripts/daemon_v0_2_control.sh start-on`
- **一键回退**
  - `./scripts/daemon_v0_2_control.sh rollback`

`rollback` 语义：停止 daemon，系统恢复到原有 batch 路径。

---

## 4. 观测指标（D4 原型）

每批次输出（daemon stdout + sqlite batch 表）：
- processed / normalized / deduped_events
- candidates / enqueued / dedup_enqueues
- throttled / skipped_hwm / errors

建议告警阈值（起步）：
- errors > 0 连续 3 批
- deduped_events 比例 > 50%
- skipped_hwm 持续增长

---

## 5. 门禁分层（D6）

### quick（开发快速回归）
- 保留核心校验
- daemon 仅跑：skeleton + feature-flag
- 跳过 closed-loop（控制时长）

### full（发布前总检）
- 包含 quick 全部
- 增加 daemon closed-loop
- 保留 system-smoke / workspace replay

### nightly（夜间长时校验）
- `governance-daemon-nightly.yml`
- 覆盖 daemon closed-loop + workspace replay
- 产物归档供次日复盘

---

## 6. 当前状态
- D1：已完成
- D2：已完成（原型级）
- D3：已完成（原型级）
- D4：已完成（原型级）
- D5：已完成（feature flag + rollback script + runbook）
- D6：已完成（门禁分层 + nightly workflow）

