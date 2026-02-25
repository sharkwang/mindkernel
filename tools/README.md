# Tools Layout

`tools/` 已按职责分层，避免单目录拥挤。

## 目录分层

### `tools/pipeline/`（主链路执行入口）
- `memory_experience_v0_1.py`
- `experience_cognition_v0_1.py`
- `cognition_decision_v0_1.py`
- `full_path_v0_1.py`

### `tools/memory/`（记忆处理与导入）
- `memory_index_v0_1.py`
- `parse_session_jsonl_v0_1.py`
- `migrate_memory_md_to_objects_v0_1.py`
- `import_memory_objects_v0_1.py`
- `llm_memory_processor_v0_1.py`

### `tools/scheduler/`（调度与确认队列）
- `scheduler_v0_1.py`
- `reflect_scheduler_worker_v0_1.py`
- `temporal_governance_worker_v0_1.py`
- `persona_confirmation_queue_v0_1.py`

### `tools/release/`（发布门禁）
- `release_check_v0_1.py`

### `tools/validation/`（统一验证脚本）
- `validate_scenarios_v0_1.py`
- `validate_memory_index_v0_1.py`
- `validate_opinion_conflicts_v0_1.py`
- `validate_recall_quality_v0_1.py`
- `validate_memory_import_v0_1.py`
- `validate_scheduler_worker_v0_1.py`
- `validate_scheduler_multi_worker_lock_v0_1.py`
- `validate_temporal_governance_worker_v0_1.py`
- `validate_scheduler_workspace_replay_v0_1.py`
- `validate_apply_compensation_v0_1.py`
- `validate_ingest_tools_v0_1.py`
- `validate_llm_memory_processor_v0_1.py`
- `system_smoke_report_v0_1.py`

### `tools/schema_runtime.py`
- 轻量 schema 运行时校验模块（共享库）

## 约定
- 默认数据库：`data/mindkernel_v0_1.sqlite`
- 运行产物（`.sqlite` / `reports/`）默认不入库
- 核心逻辑优先下沉到 `core/`；`tools/` 负责 CLI 编排与验证入口
