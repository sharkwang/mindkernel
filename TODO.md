# MindKernel TODO

_Last updated: 2026-02-21 11:00 (Asia/Shanghai)_

## P0（近期必须推进）

- [x] 将 memory index 从草案升级为可用模块（**增量 reindex**、错误恢复、去重策略）
- [x] 为 memory-index 增加 CI 校验步骤（并入现有 `critical-path-validation` workflow）
- [x] 增补 RTM：把 retain/recall/reflect + opinion evolution 的实现映射进 MR/CR/FR/NFR
- [x] 设计并实现 `memory.md` -> memory objects 的安全迁移脚本（行级 source_ref + 敏感项分级）

## P1（稳定性与治理）

- [ ] 将 reflect 作业接入 scheduler（建议式写回，默认 dry-run）
- [ ] 建立 opinion 冲突聚类与更稳健的极性判定（当前否定词启发式）
- [ ] 增加回放测试：验证 recall fact-pack 对 M→E 输入质量的影响
- [ ] 补 `memory JSONL -> objects` 导入器与幂等回放验证

## P2（后续演进）

- [ ] 评估向量检索作为 FTS 的补充（仅在规模达到阈值后）
- [ ] 形成 weekly governance report（质量指标、回滚率、升级率、学习收益）

## 今日巡检（2026-02-21）

- [x] 已完成 P0 四项落地（CI 接入、RTM 补齐、memory-index 可用性增强、`memory.md -> objects` dry-run）。
- [x] 本地回归通过：`validate_scenarios_v0_1.py` + `validate_memory_index_v0_1.py` + `system_smoke_report_v0_1.py`。
- [x] 新增 session 解析与 memory JSONL 输出脚本，为后续“会话 -> 结构化记忆”导入链路打底。

## 下一步（建议按顺序执行）

1. **P1-1** 将 reflect 作业接入 scheduler（默认 dry-run，保留人工确认写回）。
2. **P1-2** 增加 recall 质量回放基线（accuracy / recall / noise）。
3. **P1-3** 增强 opinion 冲突聚类与极性判定（替换纯否定词启发式）。
4. **P1-4** 补 `memory JSONL -> objects` 导入器与幂等回放验证。

## 风险追踪

- **发布风险（中）**：新增迁移/解析脚本尚未纳入 CI 校验矩阵，回归暴露仍可能滞后。
- **一致性风险（中）**：Reflect/Opinion evolution 仍属 Partial，治理闭环未完全自动化。
- **数据风险（中）**：迁移链路当前以 dry-run 为主，缺正式导入与错误隔离流水线。
