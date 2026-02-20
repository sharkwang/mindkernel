# Memory-Experience Prototype v0.1（先跑通前半链路）

> 目标：先把 `Memory -> Experience` 路径做成可执行原型，作为进入 Cognition 前的稳定入口。

## 1. 实现位置

- 脚本：`tools/memory_experience_v0_1.py`
- 存储：`data/mindkernel_v0_1.sqlite`

## 2. 支持命令

- `init-db`
- `ingest-memory`
- `memory-to-experience`
- `run-path`
- `list-memory`
- `list-experience`
- `list-audits`

## 3. 快速跑通（推荐）

### 3.1 使用 JSON 输入

```bash
cd /Users/zhengwang/projects/mindkernel

python3 tools/memory_experience_v0_1.py init-db

python3 tools/memory_experience_v0_1.py run-path \
  --file data/fixtures/critical-paths/08-memory-experience-path.json \
  --episode-summary "Memory converted into experience candidate" \
  --outcome "candidate generated"

python3 tools/memory_experience_v0_1.py list-memory --limit 5
python3 tools/memory_experience_v0_1.py list-experience --limit 5
python3 tools/memory_experience_v0_1.py list-audits --limit 10
```

### 3.2 使用 Markdown 输入（新增）

支持 `.md/.markdown`，可选 front matter；正文会作为 `content`。

```markdown
---
id: mem_md_001
kind: event
status: candidate
confidence: 0.78
risk_tier: low
impact_tier: medium
source_type: session
source_ref: msg://example/001
evidence_refs: ev://md/001, ev://md/002
review_due_days: 7
next_action_days: 7
---
用户明确表达了新的偏好，后续需要纳入经验层抽象。
```

如未提供部分字段，原型会自动补默认值（如 id、时间轴字段、source、evidence_refs）。

## 4. 设计对齐

- 入库时：Memory 对象必须通过 `memory.schema.json` 校验
- 生成时：Experience 对象必须通过 `experience.schema.json` 校验
- 审计时：状态迁移事件必须通过 `audit-event.schema.json` 校验
- 规则对应：Experience 候选生成遵循 `R-ME-01`

## 5. 当前边界

- 仅覆盖 Memory -> Experience
- 尚未对接 Persona Gate / Experience -> Cognition
- 冲突检测仍是简化版（只保留证据门槛）
