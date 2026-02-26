# Validation Scripts

本目录集中放置 v0.1 的验证与门禁脚本。

## 常用命令

```bash
cd /Users/zhengwang/projects/mindkernel

# 全链路场景回归
python3 tools/validation/validate_scenarios_v0_1.py

# 记忆索引与冲突聚类
python3 tools/validation/validate_memory_index_v0_1.py
python3 tools/validation/validate_opinion_conflicts_v0_1.py

# recall 与导入回放
python3 tools/validation/validate_recall_quality_v0_1.py
python3 tools/validation/validate_memory_import_v0_1.py

# 调度与补偿
python3 tools/validation/validate_scheduler_worker_v0_1.py
python3 tools/validation/validate_scheduler_multi_worker_lock_v0_1.py
python3 tools/validation/validate_scheduler_lease_renew_v0_1.py
python3 tools/validation/validate_temporal_governance_worker_v0_1.py
python3 tools/validation/validate_temporal_verify_revalidate_v0_1.py
python3 tools/validation/validate_scheduler_workspace_replay_v0_1.py
python3 tools/validation/validate_apply_compensation_v0_1.py

# 稳定化专项（R1/R5/R6）
python3 tools/validation/validate_weekly_governance_report_v0_1.py
python3 tools/validation/benchmark_scheduler_throughput_v0_1.py
python3 tools/validation/validate_scheduler_benchmark_v0_1.py
python3 tools/validation/evaluate_vector_retrieval_readiness_v0_1.py
python3 tools/validation/validate_vector_readiness_v0_1.py

# 其它验证
python3 tools/validation/validate_ingest_tools_v0_1.py
python3 tools/validation/validate_llm_memory_processor_v0_1.py
python3 tools/validation/system_smoke_report_v0_1.py

# 生成周治理报告（R1）
python3 tools/validation/generate_weekly_governance_report_v0_1.py
```

## CI 分层（R4）

- 主 workflow：`.github/workflows/critical-path-validation.yml`
  - 包含 `validate_scheduler_multi_worker_lock_v0_1.py`
  - 包含 `validate_scheduler_lease_renew_v0_1.py`
  - 包含 `validate_temporal_governance_worker_v0_1.py`
  - 包含 `validate_temporal_verify_revalidate_v0_1.py`
  - 包含 `validate_weekly_governance_report_v0_1.py`
  - 包含 `validate_scheduler_benchmark_v0_1.py`
  - 包含 `validate_vector_readiness_v0_1.py`
- 夜间/手动 workflow：`.github/workflows/governance-workspace-replay.yml`
  - 包含 `validate_scheduler_workspace_replay_v0_1.py`
  - 避免 PR 门禁时长膨胀

## release_check quick/full 分层

- `python3 tools/release/release_check_v0_1.py --quick`
  - 默认跳过：`unit-tests`、`system-smoke`、`validate-workspace-replay`
  - 适合快速回归与本地迭代
- `python3 tools/release/release_check_v0_1.py`
  - 全量执行（含 workspace replay）
  - 适合发布前总检
