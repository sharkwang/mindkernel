# Full Path Prototype v0.1（Memory→Experience→Cognition）

> 目标：串联前两段原型，形成一条可执行、可审计的一体化最小链路。

## 1. 实现位置

- 脚本：`tools/full_path_v0_1.py`
- 依赖：
  - `tools/memory_experience_v0_1.py`
  - `tools/experience_cognition_v0_1.py`

## 2. 支持命令

- `init-db`
- `run-full-path`

## 3. 运行示例

### 3.1 Pass 路径

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/full_path_v0_1.py init-db
python3 tools/full_path_v0_1.py run-full-path \
  --memory-file data/fixtures/critical-paths/08-memory-experience-path.json \
  --persona-file data/fixtures/critical-paths/10-experience-cognition-pass.json \
  --episode-summary "Planning support pattern is stable" \
  --outcome "quality improved"
```

### 3.2 Block 路径

```bash
python3 tools/full_path_v0_1.py run-full-path \
  --memory-file data/fixtures/critical-paths/08-memory-experience-path.json \
  --persona-file data/fixtures/critical-paths/11-experience-cognition-block.json \
  --episode-summary "This request is forbidden by policy" \
  --outcome "forbidden operation attempt"
```

## 4. 链路行为

1. Memory ingest（schema 校验）
2. Memory -> Experience candidate（R-ME-01）
3. Persona upsert（schema 校验）
4. Experience -> Persona Gate
5. Gate pass：创建 Cognition candidate（R-EC-01）
6. Gate block：拒绝 Cognition 升格（R-EC-02）

## 5. 当前边界

- 仍属于 v0.1 原型（单机 SQLite）
- Persona Gate 采用关键词匹配最小策略
- 尚未串联 DecisionTrace 的完整决策执行
