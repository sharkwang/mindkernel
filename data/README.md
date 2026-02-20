# Data Layout

## `fixtures/critical-paths/`

关键路径测试样例（JSON/Markdown）：

- S1~S15：覆盖 M/E/C/D、调度、Gate、回滚、高风险分流等核心场景。

## 运行时文件

- 脚本运行时会在 `data/` 下生成 `.sqlite` 数据库。
- 这些文件为临时运行产物，默认不入库。