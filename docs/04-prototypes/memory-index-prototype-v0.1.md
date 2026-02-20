# Memory Index Prototype v0.1（retain/recall/reflect）

> 目标：在 Markdown 规范源上提供离线索引与回忆能力。

## 1. 脚本

- `tools/memory_index_v0_1.py`

## 2. 支持命令

- `init-db`
- `reindex`
- `recall`
- `reflect`

## 3. 示例（使用 fixture 工作区）

```bash
cd /Users/zhengwang/projects/mindkernel

python3 tools/memory_index_v0_1.py \
  --workspace data/fixtures/memory-workspace \
  --db data/memory_index_demo.sqlite \
  reindex

python3 tools/memory_index_v0_1.py \
  --workspace data/fixtures/memory-workspace \
  --db data/memory_index_demo.sqlite \
  recall --query "MindKernel" --limit 10

python3 tools/memory_index_v0_1.py \
  --workspace data/fixtures/memory-workspace \
  --db data/memory_index_demo.sqlite \
  reflect --since-days 30 --writeback
```

## 4. 写回行为

当使用 `reflect --writeback`：
- 生成 `bank/entities/<slug>.md`
- 更新 `bank/opinions.md` 的自动区块

> v0.1 仅做建议式写回，不涉及冲突合并策略。
