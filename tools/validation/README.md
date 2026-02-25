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
python3 tools/validation/validate_temporal_governance_worker_v0_1.py
python3 tools/validation/validate_scheduler_workspace_replay_v0_1.py
python3 tools/validation/validate_apply_compensation_v0_1.py

# 其它验证
python3 tools/validation/validate_ingest_tools_v0_1.py
python3 tools/validation/validate_llm_memory_processor_v0_1.py
python3 tools/validation/system_smoke_report_v0_1.py
```
