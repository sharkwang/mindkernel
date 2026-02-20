# Contents Map (v1)

本文件用于整理 `mindkernel/docs` 当前文档结构，避免信息分散。

## 核心文档（优先阅读）

1. `requirements-and-architecture.md`
   - 主规范（需求工程基线）
   - 包含 MR/CR/FR/NFR、V&V、Traceability、Open Issues

2. `project-charter.md`
   - 项目宪法级方向与阶段目标

## 过程文档（讨论与追溯）

3. `discussion-log-2026-02-14.md`
   - 关键讨论与决策时间线
   - 用于理解“为什么会有这些条款”

4. `name-origin.md`
   - 项目命名来源（MindKernel/心智内核）

## 数据契约草案（与主规范配套）

5. `../schemas/README.md`
   - schema 草案索引与维护说明

6. `../schemas/*.schema.json`
   - `common-temporal` / `persona` / `memory` / `experience` / `cognition`

## 归档文档（只读）

7. `../archive/requirements-and-architecture.legacy.md`
   - 历史草案（从 memory-v2 迁移）

8. `../archive/design.legacy.md`
   - 早期设计草稿

9. `../archive/memory-entry.schema.legacy.json`
   - 早期 schema 草稿

## 维护规则

- 新决策：先写入 `discussion-log`，达成共识后再写入主规范。
- 主规范只保留“当前生效条款”，避免混杂历史语境。
- 归档目录只读，不再追加新条款。
