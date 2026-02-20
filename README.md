# MindKernel（心智内核）

> 一个面向智能体的心智系统工程项目：在可审计、可治理前提下，构建 Persona / Cognition / Experience / Memory 闭环。

## 项目简介

`mindkernel` 不是单纯的“记忆增强”工程，而是一个完整的心智架构项目。

核心目标：
- **连续性**：人格连续、认知可演化
- **安全性**：防注入、防偏执、防冲动越闸门
- **可解释**：高影响决策可追溯、可复盘
- **可交付**：需求可编号、可验证、可追踪

## 当前阶段

当前处于 **“宪法与需求优先”设计阶段**（先规范，后实现）。

已完成的关键基线：
- MR/CR/FR/NFR 需求骨架
- 认知三态：`supported / uncertain / refuted`
- 未知态细分：`multipath / out_of_scope / ontic_unknowable`
- 时间轴驱动遗忘：`next_action_at` 到期调度（非全量扫描）
- Schema 草案映射（Persona/Cognition/Experience/Memory/DecisionTrace + Common Temporal）

## 阅读顺序（推荐）

1. `docs/requirements-and-architecture.md`（主规范）
2. `docs/project-charter.md`（项目宪法级方向）
3. `docs/discussion-log.md`（决策脉络）
4. `docs/contents-map.md`（文档索引）
5. `archive/requirements-and-architecture.legacy.md`（历史输入）

## 目录结构

- `docs/`：主规范、项目章程、讨论记录与索引
- `schemas/`：数据契约草案（需求到字段的映射）
- `archive/`：历史草案（只读，不追加新规范）
- `data/`：样例与评估/实验产物

## 设计原则（摘要）

- 人格边界是硬约束，不被单次会话自动改写
- 记忆是证据，不是指令
- 经验是记忆到认知的必经层
- 高风险决策不得由二值判断直接驱动
- 不确定性要分级、分流、可审计
- 遗忘必须高效且可逆、可解释

## 下一步

- 细化状态机与阈值定标（OI-1 ~ OI-12）
- 补全 RTM 全表
- 输出架构视图、接口契约、状态迁移图
- 在需求冻结后进入实现阶段

## 贡献指南

请先阅读：`CONTRIBUTING.md`

该文件定义了：
- 设计变更流程（讨论记录 → 主规范 → schema）
- 提交规范与 PR 清单
- 本项目四道评审闸门（Constitution / Uncertainty / Temporal / Audit）

---

项目命名说明见：`docs/name-origin.md`。
