# MindKernel MCP Server Plugin

> 通过 MCP（Model Context Protocol）将 MindKernel 核心能力（retain / recall / reflect）暴露给外部 Agent（如 OpenClaw）。

## 背景

MindKernel 核心以 Python stdlib 实现，不依赖 Node.js。OpenClaw 是 Node.js 运行时，两者不能直接 import。

**解决方案：** 编写一个符合 MCP 协议的 Python stdio 服务器，OpenClaw 通过 `mcporter`（MCP 客户端工具）与之通信，实现零改造接入。

```
OpenClaw Agent
    ↓ mcporter call
Python MCP Server  ←→  MindKernel Core (Python)
    ↓
  SQLite / memory_items / experience_records
```

## 目录结构

```
mindkernel/plugins/mcp_server/
├── __init__.py       # 包标识
├── __main__.py       # python -m 入口
├── config.py         # 路径与环境配置
├── server.py         # MCP 协议层（JSON-RPC 2.0 over stdio）
└── tools.py          # 三个核心工具的实现
```

## 工具清单

### 1. `mindkernel_retain` — 写入记忆

将一段文本写入 MindKernel 记忆库。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | ✅ | 记忆内容原文 |
| `source` | string | ❌ | 来源标识，默认 `"openclaw"` |
| `confidence` | number | ❌ | 置信度 0.0~1.0，默认 0.5 |
| `evidence_refs` | string[] | ❌ | 证据引用列表 |
| `tags` | string[] | ❌ | 标签列表 |

**返回：** `{ok: true, memory_id: "mem_xxxxxxxxxxxx"}`

**示例：**
```bash
mcporter call mindkernel.mindkernel_retain text="王大爷今天切换到了M2.7模型"
```

---

### 2. `mindkernel_recall` — 查询记忆

查询 MindKernel 中的记忆或经验记录。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `table` | string | ❌ | `memory_items` 或 `experience_records`，默认 `memory_items` |
| `limit` | integer | ❌ | 最大返回条数，默认 20 |

**返回：** `{ok: true, table: "...", count: N, items: [...]}`

**示例：**
```bash
# 查询最近10条记忆
mcporter call mindkernel.mindkernel_recall table="memory_items" limit=10

# 查询经验记录
mcporter call mindkernel.mindkernel_recall table="experience_records"
```

---

### 3. `mindkernel_reflect` — 反思流程

对一条记忆执行反思，生成经验卡片。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `memory_id` | string | ✅ | 要反思的记忆 ID |
| `episode_summary` | string | ✅ | 对该事件的摘要描述 |
| `outcome` | string | ✅ | 结果：`positive` / `neutral` / `negative` |
| `proposals_path` | string | ❌ | reflect gate 配置文件路径 |

**返回：** `{ok: true, memory_id, experience_id, reflection: {...}}`

**示例：**
```bash
mcporter call mindkernel.mindkernel_reflect \
  memory_id="mem_xxxxxxxxxxxx" \
  episode_summary="成功将MiniMax模型从M2.5切换到M2.7" \
  outcome="positive"
```

---

## 安装与配置

### 前置条件

- Python 3.11+
- mcporter（`npm install -g mcporter`）

### 1. mcporter 配置

在 `~/.mcporter/mcporter.json` 中添加：

```json
{
  "mcpServers": {
    "mindkernel": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["/path/to/mindkernel/plugins/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/mindkernel:/path/to/mindkernel/tools"
      },
      "description": "MindKernel MCP Server"
    }
  }
}
```

> **注意**：`/path/to/mindkernel` 需替换为实际路径。

### 2. 验证安装

```bash
mcporter list
# 应显示：mindkernel — MindKernel MCP Server (retain/recall/reflect)

mcporter call mindkernel.mindkernel_recall
# 应返回数据库中的记忆列表
```

### 3. OpenClaw 集成

mcporter skill 已在 OpenClaw 全局安装。Agent 可直接调用 `mcporter call mindkernel.xxx`。

---

## MCP 协议说明

- **传输层**：stdio（标准输入/输出）
- **协议版本**：JSON-RPC 2.0
- **协议常量**：`2024-11-05`
- **通信模式**：Agent 发送 request → Server 响应 response（含 `id` 追踪）
- **工具调用**：MCP `tools/call` 映射到 server 内部函数

### 消息示例

**initialize（连接建立）**
```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}
```

**tools/list（列出所有工具）**
```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

**tools/call（调用具体工具）**
```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"mindkernel_retain","arguments":{"text":"测试记忆"}}}
```

---

## 与 OpenClaw 的集成设计

### 长期目标

OpenClaw 接收用户消息 → 实时提取记忆候选 → retain 写入 MindKernel → 需要时 recall 检索。

### 当前状态

MCP Server 已就绪，OpenClaw Agent 可通过 mcporter 直接调用。完整集成需要：
1. OpenClaw 记忆适配层（将对话历史转为 MindKernel 格式）
2. 写回策略（何时触发 retain）
3. E2E 联调测试

---

## 常见问题

**Q: mcporter 显示 server offline？**
- 检查 `~/.mcporter/mcporter.json` 中 `cwd` 或 `env.PYTHONPATH` 是否正确
- 手动运行 server 脚本验证：`PYTHONPATH=... python3 server.py`
- 检查 Python 版本：`python3 --version`（需要 3.11+）

**Q: 工具调用返回 `schema validation failed`？**
- 检查 `schemas/memory.schema.json` 是否存在
- 检查 payload 是否包含 required 字段（`id`, `status`, `text` 等由工具自动生成，可不传）

**Q: `ModuleNotFoundError: No module named 'mindkernel'`？**
- 这是因为 mindkernel 根目录没有 `__init__.py`，不是 Python 包
- 解决方案：直接用 server.py 路径运行（不要用 `-m`），并通过 `PYTHONPATH` 指定 `tools` 目录

---

## 版本历史

- **0.1.0**（2026-03-18）：初始版本，支持 retain / recall / reflect 三个核心工具
