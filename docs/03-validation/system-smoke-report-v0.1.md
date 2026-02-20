# System Smoke Report v0.1

> 用一条命令验证系统关键链路并产出报告（JSON + Markdown）。

## 脚本

- `tools/system_smoke_report_v0_1.py`

## 执行

```bash
cd /Users/zhengwang/projects/mindkernel
python3 tools/system_smoke_report_v0_1.py
```

## 输出

- 报告目录：`reports/`（运行时生成，默认不入库）
- 输出文件：
  - `reports/smoke-v0.1-<timestamp>.json`
  - `reports/smoke-v0.1-<timestamp>.md`

## 覆盖项

1. 全量关键路径校验（`validate_scenarios_v0_1.py`）
2. Full-path pass（M→E→C→D）
3. Full-path block（Persona Gate 阻断 + Decision blocked）

## 报告摘要字段

- `ok`：总结果
- `validated_objects_events`：关键路径校验对象/事件数
- `full_path_pass_outcome`
- `full_path_block_outcome`
- `steps[]`：每步耗时与返回码
