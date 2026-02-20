# Retain / Recall / Reflect Spec v0.1（草案）

## 1. Retain 语法规范

在 Markdown 中新增：

```markdown
## Retain
- W @Peter: ...
- B @warelay: ...
- O(c=0.95) @Peter: ...
- S @ProjectX: ...
```

字段语义：

- 前缀：
  - `W` = world fact
  - `B` = biographical/experience fact
  - `O` = opinion（可带置信度）
  - `S` = summary/observation
- 实体：`@EntityName`（可多个）
- `O(c=0~1)`：观点置信度（可选，默认 0.7）

解析规则（v0.1）：
- 仅解析 `## Retain` 段落中的 bullet。
- 一行一个 fact。
- source 引用格式：`relative/path.md#L<line>`。

## 2. Recall 输入输出契约

### 输入

```json
{
  "query": "planning preference",
  "kind": "O",
  "entity": "Peter",
  "since_days": 30,
  "limit": 20
}
```

### 输出（fact-pack）

```json
{
  "facts": [
    {
      "id": "fact_xxx",
      "kind": "O",
      "content": "...",
      "entities": ["Peter"],
      "confidence": 0.95,
      "source_ref": "memory/2026-02-20.md#L42",
      "observed_date": "2026-02-20"
    }
  ]
}
```

## 3. Reflect 输出规范（v0.1）

默认模式：产出建议包（不写回文件）。

```json
{
  "entity_summaries": [...],
  "opinion_candidates": [...],
  "generated_at": "..."
}
```

可选写回（`--writeback`）：
- `bank/entities/<entity>.md`
- `bank/opinions.md`（自动区块）

写回结果会在响应中返回：

```json
{
  "writeback": {
    "enabled": true,
    "paths": ["bank/entities/...", "bank/opinions.md"]
  }
}
```

## 4. 约束与安全

- 不得返回无 `source_ref` 的事实。
- 置信度仅用于排序与提示，不等于决策放行。
- Recall 层不得绕开 Persona Gate 与风险闸门。

## 5. 版本计划

- v0.1：规则抽取 + 词法 recall + reflect 建议
- v0.2：观点置信度演化（强化/冲突更新）+ 自动化 reflect 作业
