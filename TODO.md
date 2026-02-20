# MindKernel TODO

_Last updated: 2026-02-20 14:40 (Asia/Shanghai)_

## P0（近期必须推进）

- [ ] 将 memory index 从草案升级为可用模块（reindex 增量、错误恢复、去重策略）
- [ ] 增补 RTM：把 retain/recall/reflect + opinion evolution 的实现映射进 MR/CR/FR/NFR
- [ ] 为 memory-index 增加 CI 校验步骤（并入现有 critical-path workflow）
- [ ] 设计并实现 `memory.md` -> memory objects 的安全迁移脚本（行级 source_ref + 敏感项分级）

## P1（稳定性与治理）

- [ ] 将 reflect 作业接入 scheduler（建议式写回，默认 dry-run）
- [ ] 建立 opinion 冲突聚类与更稳健的极性判定（当前否定词启发式）
- [ ] 增加回放测试：验证 recall fact-pack 对 M→E 输入质量的影响

## P2（后续演进）

- [ ] 评估向量检索作为 FTS 的补充（仅在规模达到阈值后）
- [ ] 形成 weekly governance report（质量指标、回滚率、升级率、学习收益）

## 今日已完成（2026-02-20）

- [x] 项目更名与仓库统一为 `mindkernel`
- [x] docs 分类重构（01~05）与索引对齐
- [x] M→E→C→D 原型链路打通（含 Persona Gate / DecisionTrace）
- [x] 关键路径校验 15 条（62 objects/events）
- [x] retain/recall/reflect 草案与原型落地
- [x] reflect 写回 + opinion 置信度演化（v0.1.1）
- [x] 关键路径 CI 接入（critical-path-validation workflow）

## 下一步（建议按顺序执行）

1. 将 `tools/validate_memory_index_v0_1.py` 接入 CI（可先并入现有 workflow，再拆分独立 job）。
2. 补 `docs/02-design/rtm-v0.1.md` 的 memory-index 子表，覆盖 retain/recall/reflect/opinion evolution。
3. 在 `memory_index_v0_1.py` 完成三项可用性增强：
   - 增量 reindex（基于 mtime/checksum）
   - 写回与 reindex 的幂等去重
   - 异常恢复（失败文件隔离 + retry）
4. 启动 `memory.md -> objects` 迁移脚本最小版本（先 dry-run 产出映射报告）。

## 风险追踪

- **发布风险（高）**：memory-index 尚未进入 CI 守护，回归可能滞后暴露。
- **一致性风险（中）**：RTM 尚未完整覆盖新记忆层条款，需求到实现的追踪链仍有断点。
- **数据风险（中）**：尚无正式迁移脚本，`memory.md` 到结构化对象仍依赖人工过程。