# Changelog

## v0.1.0-usable（release prep）

_Date: 2026-02-25 (Asia/Shanghai)_

### Release gate status
- `v0.1.0-usable` 已完成全量发布前总检：**11/11 PASS**。
- 证据文件：
  - `reports/release_check_v0_1.json`
  - `reports/release_check_v0_1.md`

### Key additions in v0.1.0-usable
- Reflect scheduler worker loop（`tools/scheduler/reflect_scheduler_worker_v0_1.py`）与回归验证（`tools/validation/validate_scheduler_worker_v0_1.py`）。
- Opinion conflict clustering + polarity 增强（`memory_index_v0_1.py`）。
- Recall 质量基线回放验证（`tools/validation/validate_recall_quality_v0_1.py`）。
- Memory JSONL 导入器（`tools/memory/import_memory_objects_v0_1.py`、`core/memory_importer_v0_1.py`）与幂等回放验证。
- Apply compensation 失败补偿链路（`reflect_apply_compensations` + 管理命令）。
- 发布前总检聚合器（`tools/release/release_check_v0_1.py`）与发布手册。

### RC delta（rc1 → rc3）
- `rc1 -> rc2`
  - `52e8eca` docs: refresh quickstart path and expand naming origin note
  - `6e2b1c8` fix: stabilize scheduler worker validation timing
  - `aef0e5a` docs: finalize daily plan and mark S10/S11 rc1 completed
- `rc2 -> rc3`
  - `c530efb` refactor: layer tools into pipeline/memory/scheduler/release and fix references
  - `019d899` refactor: organize validation scripts under `tools/validation`

### Compatibility / rollback
- 兼容性：本次以工具分层与验证路径稳定化为主，无 schema 破坏性变更。
- 回滚建议：若正式发布后发现回归，优先回退到 `v0.1.0-usable-rc3` 或 `v0.1.0-usable-rc2`，并重新执行 `release_check_v0_1.py` 确认基线。