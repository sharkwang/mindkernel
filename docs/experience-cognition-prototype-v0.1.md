# Experience-Cognition Prototype v0.1（含 Persona Gate 最小实现）

> 目标：先跑通 `Experience -> Cognition` 的最小升格路径，并实现可解释的 Persona 冲突闸门。

## 1. 实现位置

- 脚本：`tools/experience_cognition_v0_1.py`
- 存储：`data/mindkernel_v0_1.sqlite`

## 2. 支持命令

- `init-db`
- `upsert-persona`
- `ingest-experience`
- `experience-to-cognition`
- `run-path`
- `list-experience`
- `list-cognition`
- `list-persona`
- `list-audits`

## 3. Persona Gate（最小实现）

- 输入：`persona.boundaries` + experience 文本域（`episode_summary/outcome/action_taken`）
- 机制：关键词冲突匹配（大小写不敏感）
- 输出：
  - `pass`：允许升格，生成 Cognition candidate（R-EC-01）
  - `block`：拒绝升格，记录 gate 阻断事件（R-EC-02）

## 4. 快速跑通

### 4.1 通过路径（Pass）

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/experience_cognition_v0_1.py init-db
python3 tools/experience_cognition_v0_1.py run-path \
  --persona-file data/fixtures/critical-paths/10-experience-cognition-pass.json \
  --experience-file data/fixtures/critical-paths/10-experience-cognition-pass.json
```

### 4.2 阻断路径（Block）

```bash
python3 tools/experience_cognition_v0_1.py run-path \
  --persona-file data/fixtures/critical-paths/11-experience-cognition-block.json \
  --experience-file data/fixtures/critical-paths/11-experience-cognition-block.json
```

## 5. 设计对齐

- Persona / Experience / Cognition 均走 schema 校验
- 审计事件走 `audit-event.schema.json` 校验
- 规则对齐：
  - R-EC-01：Persona Gate pass -> Cognition candidate
  - R-EC-02：Persona 冲突 -> block + 审计
