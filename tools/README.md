# Tools Overview

为避免 `tools/` 根目录过于拥挤，脚本已按职责分层：

## 1) 业务/执行入口（保留在 `tools/` 根目录）

- `memory_experience_v0_1.py` — Memory ingest + Memory→Experience
- `experience_cognition_v0_1.py` — Experience→Cognition + Persona Gate
- `cognition_decision_v0_1.py` — Cognition→DecisionTrace
- `full_path_v0_1.py` — M→E→C→D 一键链路
- `memory_index_v0_1.py` — retain/recall/reflect 索引原型
- `scheduler_v0_1.py` — 调度原型（enqueue/pull/ack/fail + route-proposals）
- `reflect_scheduler_worker_v0_1.py` — reflect worker loop（pull->execute->ack/fail）
- `persona_confirmation_queue_v0_1.py` — 人格冲突确认队列 + apply-plan/apply-exec + compensation 管理
- `parse_session_jsonl_v0_1.py` — session JSONL -> memory events
- `migrate_memory_md_to_objects_v0_1.py` — memory.md 迁移 dry-run
- `import_memory_objects_v0_1.py` — memory JSONL 导入器
- `llm_memory_processor_v0_1.py` — LLM 记忆抽取处理
- `release_check_v0_1.py` — 发布前总检聚合脚本
- `schema_runtime.py` — 轻量 schema 运行时校验模块

## 2) 校验脚本（统一放到 `tools/validation/`）

- `validation/validate_scenarios_v0_1.py`
- `validation/validate_memory_index_v0_1.py`
- `validation/validate_opinion_conflicts_v0_1.py`
- `validation/validate_recall_quality_v0_1.py`
- `validation/validate_memory_import_v0_1.py`
- `validation/validate_scheduler_worker_v0_1.py`
- `validation/validate_apply_compensation_v0_1.py`
- `validation/validate_ingest_tools_v0_1.py`
- `validation/validate_llm_memory_processor_v0_1.py`
- `validation/system_smoke_report_v0_1.py`

## 3) 约定

- 默认数据库：`data/mindkernel_v0_1.sqlite`
- 运行产物（`.sqlite` / `reports/`）默认不入库
- 核心逻辑尽量下沉到 `core/`，`tools/` 保持 CLI/流程编排职责
