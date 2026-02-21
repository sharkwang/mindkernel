# LLM Memory Processor Prototype v0.1（外部模型记忆处理核心对象）

> 目标：提供一个可复用核心对象，调用外部 LLM 将原始文本转为 `memory.schema` 兼容对象。

## 1. 实现位置

- 核心对象：`tools/llm_memory_processor_v0_1.py`
- 类名：`LLMMemoryProcessor`
- 配置对象：`LLMProcessorConfig`

## 2. 支持后端

- `mock`：本地规则模拟（默认用于测试/CI）
- `openai_compatible`：OpenAI-compatible chat completions HTTP 接口

> 默认 endpoint：`https://api.openai.com/v1/chat/completions`

## 3. 核心能力

1. **调用外部 LLM 抽取记忆候选**
   - 输入：原始文本 + `source_ref`
   - 输出：`memory_items[]`
2. **自动补全 memory 必需字段**
   - `id / source / evidence_refs / status / created_at / review_due_at / next_action_at`
3. **schema 校验**
   - 逐条执行 `memory.schema.json` 校验
4. **稳定 ID 与去重**
   - `id = sha1(source_ref|content)`
   - 按 content 去重

## 4. 快速使用

### 4.1 mock 模式（推荐先跑）

```bash
cd /Users/zhengwang/projects/mindkernel

python3 tools/llm_memory_processor_v0_1.py \
  --backend mock \
  --model mock-v0 \
  --source-ref session://sample-session-001#msg:u1 \
  --text-file data/fixtures/llm-memory/sample-memory-input.txt \
  --out reports/llm-memory-extract-demo.json \
  --jsonl-out reports/llm-memory-extract-demo.memory.jsonl
```

### 4.2 外部 LLM 模式（OpenAI-compatible）

```bash
export OPENAI_API_KEY=...  # 或自定义 --api-key-env

python3 tools/llm_memory_processor_v0_1.py \
  --backend openai_compatible \
  --model gpt-4o-mini \
  --source-ref session://prod-session#msg:123 \
  --text "用户要求下周前完成 CI 门禁固化，并补 recall 质量基线。"
```

## 5. 校验脚本

```bash
python3 tools/validate_llm_memory_processor_v0_1.py
```

校验内容：
- 核心对象可运行（mock backend）
- 输出条目数符合预期
- 产出 JSONL 逐条通过 `memory.schema.json`

## 6. v0.1 边界

- 仅做“抽取与结构化”，不直接写入主数据库
- 不做跨模型 ensemble
- 不做向量检索与语义回放评估（留给 S8/S9）
