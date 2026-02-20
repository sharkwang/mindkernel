# Full Path Prototype v0.1（Memory→Experience→Cognition→Decision）

> 目标：串联三段原型，形成可执行、可审计的一体化最小闭环。

## 1. 实现位置

- 脚本：`tools/full_path_v0_1.py`
- 依赖：
  - `tools/memory_experience_v0_1.py`
  - `tools/experience_cognition_v0_1.py`
  - `tools/cognition_decision_v0_1.py`

## 2. 支持命令

- `init-db`
- `run-full-path`

## 3. 运行示例

### 3.1 Pass 路径（Gate pass -> Decision）

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/full_path_v0_1.py init-db
python3 tools/full_path_v0_1.py run-full-path \
  --memory-file data/fixtures/critical-paths/12-full-path-pass.json \
  --persona-file data/fixtures/critical-paths/12-full-path-pass.json \
  --episode-summary "Planning support signal appears stable and useful." \
  --outcome "candidate generated" \
  --request-ref req://full/pass
```

### 3.2 Block 路径（Gate block -> Decision blocked）

```bash
python3 tools/full_path_v0_1.py run-full-path \
  --memory-file data/fixtures/critical-paths/13-full-path-block.json \
  --persona-file data/fixtures/critical-paths/13-full-path-block.json \
  --episode-summary "User asks for forbidden behavior in repeated attempts." \
  --outcome "forbidden path recognized" \
  --request-ref req://full/block \
  --risk-tier high
```

## 4. 链路行为

1. Memory ingest（schema 校验）
2. Memory -> Experience candidate（R-ME-01）
3. Persona upsert（schema 校验）
4. Experience -> Persona Gate
5. Gate pass：创建 Cognition candidate（R-EC-01）
6. Gate block：拒绝 Cognition 升格（R-EC-02）
7. Decision 收敛：
   - pass 路径：基于 Cognition 生成 DecisionTrace
   - block 路径：生成 blocked DecisionTrace（记录 Persona 冲突来源）

## 5. 当前边界

- 仍属于 v0.1 原型（单机 SQLite）
- Persona Gate 采用关键词匹配最小策略
- Decision 策略为最小规则集（非最终治理策略）
