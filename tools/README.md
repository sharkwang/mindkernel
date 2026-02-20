# Tools Overview

本目录存放 v0.1 原型脚本。

## 核心链路脚本

- `memory_experience_v0_1.py`
  - Memory ingest + Memory→Experience
- `experience_cognition_v0_1.py`
  - Experience→Cognition + Persona Gate（最小实现）
- `cognition_decision_v0_1.py`
  - Cognition→DecisionTrace
- `full_path_v0_1.py`
  - M→E→C→D 一键全链路

## 基础能力脚本

- `scheduler_v0_1.py`
  - 到期调度原型（enqueue/pull/ack/fail/stats）
- `validate_scenarios_v0_1.py`
  - fixtures + 业务断言校验
- `system_smoke_report_v0_1.py`
  - 一键执行烟测并输出报告
- `schema_runtime.py`
  - 轻量运行时 schema 校验模块
- `memory_index_v0_1.py`
  - 离线记忆索引草案（retain/recall/reflect）

## 备注

- 所有脚本默认数据库路径：`data/mindkernel_v0_1.sqlite`
- 运行中生成的 `.sqlite` 与 `reports/` 内容默认不入库。
