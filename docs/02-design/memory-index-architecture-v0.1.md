# Memory Index Architecture v0.1（草案）

> 目标：在不破坏 Markdown 作为规范源的前提下，补齐离线 Recall/Reflect 能力。

## 1. 设计原则

1. **Markdown 为真相源（SoT）**：`memory/*.md`、`memory.md`、`bank/*.md` 人类可读可审计。
2. **索引可重建**：`.memory/index.sqlite` 仅为派生层，可随时 reindex 重建。
3. **离线优先**：默认仅本地 SQLite + FTS5。
4. **证据可追溯**：所有 recall 结果必须携带 `source = path#line`。
5. **与治理闭环解耦**：索引负责 Recall；M/E/C/D 负责决策与治理。

## 2. 工作区布局（建议）

```text
<workspace>/
  memory.md
  memory/
    YYYY-MM-DD.md
  bank/
    world.md
    experience.md
    opinions.md
    entities/
      <entity>.md
  .memory/
    index.sqlite
```

## 3. 索引数据模型（v0.1）

- `documents`
  - `path` / `sha1` / `mtime` / `indexed_at`
- `facts`
  - `id` / `kind` / `content` / `entities` / `confidence`
  - `source_path` / `line_no` / `source_ref`
  - `observed_date` / `indexed_at`
- `facts_fts`（FTS5）
  - `content` / `entities` / `kind` / `fact_id`

> 说明：v0.1 不引入向量索引；先做词法 + 元数据过滤。

## 4. 处理流程

### 4.1 Retain（抽取）

- 解析每日日志中的 `## Retain` 段落。
- 仅抽取结构化要点（见 `retain-recall-reflect-spec-v0.1.md`）。
- 未命中 Retain 的内容不默认入索引（避免噪声）。

### 4.2 Recall（检索）

- Query 入口：`query + kind + entity + since_days + limit`
- 检索策略：
  1) FTS5 词法命中
  2) kind/entity/time 过滤
  3) 按 `observed_date DESC, indexed_at DESC` 排序

### 4.3 Reflect（反思）

- 从近期事实中汇总实体视图和观点候选。
- v0.1 仅输出建议，不强制自动回写。
- 后续可接 scheduler 形成周期作业。

## 5. 与现有 M→E→C→D 的集成点

1. Recall 返回 `fact-pack`（含 `source_ref`）供 Memory ingest。
2. Reflect 结果可更新 `bank/opinions.md` 与 `bank/entities/*.md`。
3. DecisionTrace 引用 recall 的 `source_ref`，形成跨层证据链。

## 6. v0.1 / v0.2 边界

- v0.1：SQLite + FTS5 + Retain 语法 + CLI 草案
- v0.2：向量召回、冲突合并、opinion 置信度演化、自动 reflect 回写

## 7. 验收建议

- 至少 3 个 memory 样例可被 reindex + recall 命中。
- recall 结果 100% 带 `source_ref`。
- reindex 支持全量重建与增量覆盖。