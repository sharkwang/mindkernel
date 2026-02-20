# Schemas (Draft)

这些是 MindKernel 的**数据契约草案**（draft），用于需求对齐与接口讨论。

- 当前状态：设计中（non-production）
- 作用：把 `docs/requirements-and-architecture.md` 中的 CR/FR/NFR 映射为可检查结构

## 文件
- `common-temporal.schema.json`：统一时间轴字段
- `persona.schema.json`：人格层对象
- `memory.schema.json`：记忆层对象
- `experience.schema.json`：经验层对象
- `cognition.schema.json`：认知层对象

## 注意
- 字段会根据后续评审（特别是 OI-1~OI-12）继续调整。
- 这些 schema 不代表最终实现存储结构，只代表 v1 设计意图。
