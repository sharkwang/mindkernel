# Validation Critical Paths v0.1（关键路径验证）

> 目标：把 v0.1 的关键治理路径变成可重复验证的固定资产（fixtures + 脚本）。

## 1. 资产位置

- Fixtures：`data/fixtures/critical-paths/*.json`
- 校验脚本：`tools/validate_scenarios_v0_1.py`

## 2. 覆盖的关键路径

1. **S1 Happy Path**
   - 文件：`01-happy-path.json`
   - 覆盖：Memory→Experience→Cognition→Decision 正常闭环
2. **S2 Poison Rollback**
   - 文件：`02-poison-rollback.json`
   - 覆盖：注入确认、级联回滚、审计追踪
3. **S3 Uncertain TTL Routing**
   - 文件：`03-uncertain-ttl-routing.json`
   - 覆盖：`uncertain` 到期分流、预算耗尽降级、调度触发
4. **S4 High-Risk Block**
   - 文件：`04-high-risk-block.json`
   - 覆盖：高风险 + uncertain 直接执行拦截
5. **S5 Reinstate**
   - 文件：`05-reinstate.json`
   - 覆盖：新证据触发 `stale+uncertain -> active+supported`
6. **S6 Scheduler Retry**
   - 文件：`06-scheduler-retry.json`
   - 覆盖：运行中失败后重试回队（attempt 递增）
7. **S7 Scheduler Dead Letter**
   - 文件：`07-scheduler-dead-letter.json`
   - 覆盖：超过重试上限后进入 `dead_letter`
8. **S8 Memory→Experience Path**
   - 文件：`08-memory-experience-path.json`
   - 覆盖：记忆入库到经验候选生成（R-ME-01）
9. **S9 Markdown Memory Input**
   - 文件：`09-memory-markdown.md`
   - 覆盖：Markdown（front matter + 正文）转换为合法 Memory 对象

## 3. 校验内容

脚本执行两层校验：

- **Schema 层**：
  - `memory` / `experience` / `cognition` / `decision-trace` / `audit-event`
- **业务断言层**：
  - S2 必须出现 `rejected_poisoned` + rollback 事件
  - S3 必须出现 `status=stale + epistemic_state=uncertain`
  - S4 高风险结果禁止 `executed`
  - S5 必须体现前后状态回升
  - S6 必须出现 retry 回队（`queued` 且 `attempt=1`）
  - S7 必须出现 `dead_letter` 终态
  - S8 必须体现 Memory 与 Experience 的引用链一致
  - S9 Markdown 输入必须转化为合法 Memory（含 content 与 evidence_refs）

## 4. 运行方式

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/validate_scenarios_v0_1.py
```

成功输出示例：

- `PASS 01-happy-path.json`
- ...
- `PASS 09-memory-markdown.md`
- `All good. Validated objects/events: 33`

## 5. CI 自动校验

- GitHub Actions 工作流：`.github/workflows/critical-path-validation.yml`
- 触发条件：
  - push 到 `main`（当 schemas/docs/fixtures/validator/workflow 变更时）
  - pull request（同上路径）
  - 手动触发（workflow_dispatch）
- 执行动作：运行 `python3 tools/validate_scenarios_v0_1.py`

## 6. 维护规则

- 新增关键场景时：
  1) 增加 fixture
  2) 在脚本中补断言
  3) 更新本文件覆盖列表
- 任何 schema 字段变更后，必须先跑一次本脚本再提交。
