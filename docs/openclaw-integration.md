# MindKernel × OpenClaw 集成方案

> 本文档描述如何通过 MCP（Model Context Protocol）将 MindKernel 的记忆能力接入 OpenClaw Agent。

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│                   OpenClaw Agent                       │
│   (Memory Adapter: 对话历史 → MindKernel retain 格式)  │
└──────────────────────┬───────────────────────────────┘
                       │ mcporter call
                       ▼
┌──────────────────────────────────────────────────────┐
│               mcporter (MCP Client)                    │
│   ~/.mcporter/mcporter.json                           │
└──────────────────────┬───────────────────────────────┘
                       │ stdio (JSON-RPC 2.0)
                       ▼
┌──────────────────────────────────────────────────────┐
│         MindKernel MCP Server (Python)                │
│   plugins/mcp_server/server.py                        │
│   ├── mindkernel_retain   (写记忆)                    │
│   ├── mindkernel_recall   (读记忆)                    │
│   └── mindkernel_reflect  (反思生成经验)               │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              MindKernel Core (Python)                 │
│   core/memory_experience_core_v0_1.py                 │
│   core/reflect_gate_v0_1.py                          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
              data/mindkernel_v0_1.sqlite
```

## 接入进度

| 组件 | 状态 | 说明 |
|------|------|------|
| MCP Server (`server.py`) | ✅ 完成 | JSON-RPC 2.0 stdio，已验证 |
| 三个核心工具 | ✅ 完成 | retain / recall / reflect |
| mcporter 配置 | ✅ 完成 | `~/.mcporter/mcporter.json` |
| OpenClaw mcporter skill | ✅ 完成 | 全局已安装 |
| **记忆适配层** | ✅ 完成 | `skills/mindkernel-retain/retain.py` + cron |
| **Daemon 对接** | ✅ 完成 | `openclaw_event_adapter.py` + daemon `--feature-flag on` |
| **launchd 自启** | ✅ 完成 | 3个 plist 已加载 |
| **Reflect Worker** | ✅ 完成 | scheduler queue → experience 生成 |
| 写回策略 | 🔲 待办 | 经验卡片写回 OpenClaw 对话 |

## 快速验证

```bash
# 1. 列出工具
mcporter list mindkernel

# 2. 查询已有记忆
mcporter call mindkernel.mindkernel_recall table="memory_items" limit=5

# 3. 写入一条测试记忆
mcporter call mindkernel.mindkernel_retain \
  text="通过MCP接入了OpenClaw" \
  source="openclaw" \
  tags='["integration","test"]'

# 4. 查看刚写入的记录
mcporter call mindkernel.mindkernel_recall table="memory_items" limit=1
```

## 记忆适配层设计（待实现）

### 触发时机

OpenClaw 每次响应用户消息后，评估是否值得 retain：

- **高价值触发**（直接 retain）：
  - 用户提供了新事实、数据、决定
  - 用户更正了之前的错误
  - 明确的偏好或习惯表达

- **批量触发**（Daemon 定时）：
  - 每日对话摘要
  - 高频模式识别后写入

### retain 格式映射

| OpenClaw 对话事件 | MindKernel payload |
|-------------------|---------------------|
| 用户消息原文 | `text` |
| 消息来源（telegram/feishu）| `source` |
| 时间戳 | `created_at` |
| 消息ID | 存入 `evidence_refs` |
| 提取的实体/标签 | `tags` |

### 示例流程

```
用户: "我下周要去北京出差"
         ↓
OpenClaw 拦截消息
         ↓
记忆候选评估 → 触发 retain
         ↓
mcporter call mindkernel.mindkernel_retain
  text="用户计划下周（2026-03-24起）去北京出差"
  source="telegram"
  tags='["travel","plan"]'
         ↓
MindKernel SQLite 写入
```

## 下一步

1. **记忆适配层**：写一个 OpenClaw skill（`mindkernel-memory-adapter`），在每次对话后做候选评估
2. **Daemon 协同**：复用 MindKernel 的 `memory_observer_daemon` 对齐观察 OpenClaw 的对话流
3. **经验卡片**：用户确认某段记忆后，触发 `reflect` 生成 Experience 卡片

---

> 文档更新时间：2026-03-18
