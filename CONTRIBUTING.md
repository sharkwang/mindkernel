# Contributing to MindKernel（心智内核）

感谢你参与本项目。

本仓库当前处于 **“先宪法/需求，后实现”** 阶段，请优先保证规范一致性与可追溯性。

---

## 1. 贡献范围

当前欢迎的贡献类型：

- 需求条款优化（MR / CR / FR / NFR）
- Traceability（需求追踪）完善
- Open Issues 的定标方案与验证方案
- Schema 草案与需求字段映射修正
- 文档结构整理（可读性、可审计性）

暂不优先：

- 跳过需求基线直接提交复杂实现
- 未对齐主规范的“先写代码后补文档”变更

---

## 2. 设计变更流程（必须）

涉及设计/规则的变更，请按顺序：

1. 先写讨论记录（`docs/discussion-log-*.md`）
2. 再更新主规范（`docs/requirements-and-architecture.md`）
3. 若字段变化，必须同步更新 `schemas/*.schema.json`
4. 同步更新 `docs/contents-map.md`（若目录或阅读路径变化）

> 原则：**先决策，后固化；先规范，后实现。**

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

示例：

- `docs: add temporal forgetting variables baseline`
- `feat: add cognition unknown_type routing constraints`

---

## 4. Pull Request 评审清单

提交 PR 前，请自查：

- [ ] 变更目的清晰（为什么要改）
- [ ] 标注受影响需求 ID（如 `CR-12`, `FR-18`）
- [ ] Traceability 已同步更新（若有需求关系变化）
- [ ] 若字段变化，schema 已同步
- [ ] 未在无必要情况下修改 `archive/`（归档目录默认只读）
- [ ] Open Issues 已更新（若引入新未决项）

---

## 5. 本项目的四道评审闸门

1. **Constitution Gate**：是否违反 CR 硬约束？
2. **Uncertainty Gate**：是否正确处理 `epistemic_state` / `unknown_type`？
3. **Temporal Gate**：涉及遗忘时，是否遵循时间轴与 `next_action_at` 到期调度？
4. **Audit Gate**：高影响结论是否可追溯、可解释、可回滚？

---

## 6. 本地检查建议

在提交前可执行：

```bash
python3 - <<'PY'
import json,glob
for p in glob.glob('schemas/*.json'):
    json.load(open(p))
print('schema json parse: OK')
PY
```

---

## 7. 沟通风格

- 讨论问题：鼓励直接、具体、可验证
- 争议处理：以需求条款与验收标准为准
- 目标导向：减少空泛争论，优先形成可执行变更

---

如需发起较大结构改动，建议先开一个“设计提案”文档，再进入主规范修改。
