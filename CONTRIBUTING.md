# Contributing to MindKernel（心智内核）

感谢你参与本项目。

本仓库当前处于 **v0.1「规范 + 原型并行」** 阶段：
- 任何实现变更都要能回链到规范与验证；
- 任何规范变更都要同步契约与测试资产。

---

## 1. 贡献范围

当前欢迎：

- 需求条款优化（MR / CR / FR / NFR）
- Traceability（RTM）完善
- Schema 草案与字段映射修正
- 原型链路增强（M/E/C/D、调度、审计）
- 关键路径 fixtures / 断言 / CI 校验增强
- 文档结构与可读性整理

不接受：

- 跳过规范基线、无可追溯依据的“拍脑袋实现”
- 仅改代码不补文档/契约/验证的破链变更

---

## 2. 设计变更流程（必须）

涉及设计/规则的变更，请按顺序：

1. 先写讨论记录（`docs/05-history/discussion-log.md`）
2. 再更新主规范（`docs/01-foundation/requirements-and-architecture.md`）
3. 若字段变化，必须同步更新 `schemas/*.schema.json`
4. 同步更新验证资产（fixtures / 断言 / CI）
5. 若目录或阅读顺序变化，更新 `docs/contents-map.md`

> 原则：**先决策，后固化；先规范，后实现；改实现必带验证。**

---

## 3. 分支与提交规范

### 分支命名建议

- `docs/<topic>`
- `feat/<topic>`
- `fix/<topic>`
- `chore/<topic>`

### Commit 规范（建议 Conventional Commits）

- `docs: ...`
- `feat: ...`
- `fix: ...`
- `chore: ...`
- `refactor: ...`

---

## 4. Pull Request 自查清单

- [ ] 变更目的清晰（为什么要改）
- [ ] 标注受影响需求 ID（如 `CR-12`, `FR-18`）
- [ ] RTM/Traceability 已同步（若需求关系变化）
- [ ] schema 已同步（若字段变化）
- [ ] fixtures / 断言 / CI 已同步（若行为变化）
- [ ] 未在无必要情况下修改 `archive/`（归档目录默认只读）

---

## 5. 四道评审闸门

1. **Constitution Gate**：是否违反 CR 硬约束？
2. **Uncertainty Gate**：是否正确处理 `epistemic_state` / `unknown_type`？
3. **Temporal Gate**：是否遵循 `next_action_at` 到期调度？
4. **Audit Gate**：是否可追溯、可解释、可回滚？

---

## 6. 本地检查建议

```bash
# schema + 关键路径
python3 tools/validate_scenarios_v0_1.py

# 系统烟测报告
python3 tools/system_smoke_report_v0_1.py
```
