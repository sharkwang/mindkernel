# Core Conventions (keep it clean)

1. **只放验证通过的核心逻辑**
   - 可复用、无交互副作用、可被 CLI/service 调用。
2. **不放运行产物**
   - 禁止 `.sqlite/.jsonl/report/demo` 等数据文件进入 `core/`。
3. **CLI 与核心分离**
   - 参数解析/打印在 `tools/`，业务逻辑在 `core/`。
4. **命名规则**
   - `*_v0_1.py`：与当前原型版本一致。
5. **每个核心模块必须有最小回归验证**
   - 至少 1 个命令或脚本可证明功能可用。
