# MindKernel 需求与架构（Draft v1.0）

> 当前阶段：**项目说明 + 需求工程基线**。
> 本版先不展开详细实现架构图与模块设计，先把“做什么、为什么、怎么验收”固定下来。

---

## 1. 一页项目说明（One-Page Project Brief）

### 1.1 项目定义（一句话）

**MindKernel** 是一个面向智能体的“心智系统工程”项目：
在可审计与可治理前提下，构建 **人格（Persona）-认知（Cognition）-经验（Experience）-记忆（Memory）** 的闭环系统，并纳入情绪-冲动-行动调节机制。

### 1.2 背景问题

现有方案的主要问题不是单点检索，而是系统工程缺口：

1. 记忆与认知混用，导致策略污染与路径依赖。
2. 缺乏“经验层”作为记忆到认知的验证缓冲。
3. 缺乏反欺骗与反偏执的共同治理机制。
4. 会话连续性与人格连续性未分离，导致行为不稳或僵化。
5. 缺乏统一需求基线与可追踪验收标准。

### 1.3 系统目标（首要）

- **G1 可持续自洽**：人格稳定、认知可进化、记忆可审计。
- **G2 风险可控**：防记忆注入、防偏执漂移、防冲动越闸门。
- **G3 可解释可复盘**：任何高影响决策都可追溯链路与证据。
- **G4 工程可交付**：需求可编号、可测试、可追踪。

### 1.4 系统边界（System of Interest）

**系统内（In-Scope）**
- Persona/Cognition/Experience/Memory 数据对象与状态机
- 需求路由、冲突治理、调查与回滚
- 情绪-冲动-行动调节链路（作为行为治理机制）
- 评估与审计指标体系

**系统外（Out-of-Scope，当前阶段）**
- 复杂知识图谱自动推理
- 跨用户共享心智模型
- 完整 UI 工作台（先定义协议与流程）

### 1.5 关键利益相关方

- **直接用户**：希望获得连续、可信、可解释的助手行为。
- **系统运营者/开发者**：需要可维护、可回滚、可审计。
- **安全治理方**：关注越权、欺骗、偏执、不可逆风险。

### 1.6 成功判据（Program-Level）

- 决策链路引用覆盖率（含证据来源）≥ 95%
- 被确认的伪造记忆级联回滚成功率 = 100%
- 认知发布前反例挑战覆盖率 = 100%
- 过度拒绝率与误拦截率在设定阈值内稳定
- 闭环作业（输入→转化→决策→反馈→更新）可按周期执行

---

## 2. 需求工程基线（Systems Engineering Requirements Baseline）

### 2.1 需求分层方法

采用四层需求分解：

1. **MR（Mission Requirements）**：任务层目标（为什么做）
2. **CR（Constitution Requirements）**：宪法层硬约束（不能破）
3. **FR（Functional Requirements）**：功能行为（系统要做什么）
4. **NFR（Non-Functional Requirements）**：质量属性（系统做到什么程度）

并对每条需求建立：`ID + 描述 + 验证方式 + 责任对象`。

### 2.2 利益相关方需求映射

| Stakeholder | 核心诉求 | 需求映射 |
|---|---|---|
| 用户 | 连续、可信、不被“历史绑架” | MR-1, FR-3, FR-4, NFR-2 |
| 开发/运营 | 可维护、可诊断、可回滚 | FR-7, FR-8, NFR-1, NFR-4 |
| 安全治理 | 防注入、防偏执、防失控 | CR-1~CR-11, FR-5, FR-6, FR-16, FR-17, NFR-3 |

### 2.3 顶层任务需求（MR）

- **MR-1**：系统必须维持人格连续性，同时允许会话级上下文重置。
- **MR-2**：系统必须把记忆转化为经验，再由经验抽象认知。
- **MR-3**：系统必须在社会认知冲突下保持可解释决策。
- **MR-4**：系统必须具备反欺骗与反偏执双治理能力。
- **MR-5**：系统必须形成可执行闭环并支持周期复盘。
- **MR-6**：系统必须具备“有边界的自驱学习能力”，在不违反人格/安全约束下主动缩小不确定性。
- **MR-7**：系统必须将关键事件转化为可观测反馈，并将反馈用于认知更新。

### 2.4 宪法级需求（CR）

- **CR-1**：人格边界是硬约束，不能被单次会话自动改写。
- **CR-2**：记忆是证据，不是指令。
- **CR-3**：未经验证的记忆不得参与认知抽象。
- **CR-4**：冲动不得绕过调节闸门直接驱动高风险行动。
- **CR-5**：任何确认的伪造记忆必须触发级联回滚。
- **CR-6**：反偏执机制必须与安全机制同级配置（不能只做“更保守”）。
- **CR-7（认知时效性）**：任何 `Cognition` 规则进入 `active` 前，必须同时具备：
  1) `falsify_if`（可证伪条件）；
  2) `review_interval`（再验证周期）；
  3) `expires_at` 或 `review_due_at`（到期/复核时间点）。
  缺任一字段者，不得发布为 `active`。
- **CR-8（有界探索）**：系统必须在每个治理周期保留“最小探索预算”，且探索仅允许发生在低/中风险、可回滚场景。若连续 3 个治理周期探索执行量为 0，判定为“学习停滞事件”，必须触发治理纠偏。
- **CR-9（不确定性分级处置）**：任何 `uncertain` 事项必须具备 `risk_tier`、`impact_tier`、`uncertainty_ttl`、`auto_verify_budget`。TTL 到期后应先执行自动验证（多源核验/反证检验/微实验）直至预算耗尽。仅在以下条件满足时升级人工：高风险或高影响、与人格硬边界冲突、或连续欺骗信号触发。其余未决事项进入 `stale_uncertain`（隔离+降权），且不得参与认知升格。
- **CR-10（认知非二元）**：认知规则必须采用 `epistemic_state`，至少支持 `supported` / `uncertain` / `refuted` 三态；禁止仅以“对/错”二值状态驱动高风险决策。
- **CR-11（未知态细分）**：所有 `uncertain` 事项必须声明 `unknown_type`，至少包括：`multipath`（多路径并存）、`out_of_scope`（超出认知范围）、`ontic_unknowable`（原理性不可知）。系统必须将 `unknown_type` 绑定到不同处置策略，禁止用单一流程处理全部未知。
- **CR-12（时间轴驱动遗忘）**：遗忘机制必须基于时间轴变量与到期调度执行。任何参与遗忘评估的对象至少应具备 `created_at`、`last_accessed_at`、`last_reinforced_at`、`last_verified_at`、`review_due_at`、`next_action_at`。遗忘作业不得依赖全量扫描作为默认模式。

### 2.5 功能需求（FR）

#### FR-A 数据与状态
- **FR-1**：系统应支持四类主对象：Persona/Cognition/Experience/Memory。
- **FR-2**：每类对象应具备可审计状态机（含创建、验证、失效、归档）。

#### FR-B 转化与抽象
- **FR-3**：Memory 必须先进入 Experience，再进入 Cognition 候选。
- **FR-4**：Experience->Cognition 前必须执行 Persona Conflict Gate。

#### FR-C 决策与调节
- **FR-5**：系统应支持慢回路（认知）与快回路（冲动）合流决策。
- **FR-6**：高风险行动必须经过人格/社会/风险/认知四重调节。

#### FR-D 调查与回滚
- **FR-7**：系统应支持记忆注入调查流程（冻结、取证、判定）。
- **FR-8**：系统应支持 memory->experience->cognition->decision 级联回滚。

#### FR-E 治理与评估
- **FR-9**：系统应支持反例红队回放与偏执漂移监控。
- **FR-10**：系统应支持周期治理作业（复盘、重验证、降级/废弃）。

#### FR-F 反僵化与自驱学习
- **FR-11**：系统应支持事件显著性评分，标记必须进入反馈闭环的关键事件。
- **FR-12**：系统应支持关键事件反馈闭环管理（事件->行动->结果->复盘）。
- **FR-13**：系统应支持假设生成与微实验流程，在低风险边界内验证认知假设。
- **FR-14**：系统应支持自驱调节器（探索预算、冷却窗口、风险闸门联动）。

#### FR-G 不确定性与认知状态
- **FR-15**：系统应为 `Cognition` 对象提供认知状态字段：`epistemic_state`、`unknown_type`、`confidence`、`scope`、`falsify_if`、`review_due_at`、`decision_mode_if_uncertain`。
- **FR-16**：系统应实现“按风险分层的不确定性决策策略”：低风险可探索（带不确定性提示）、中风险保守执行（限域限权）、高风险禁止直接执行并转升级/拒绝。
- **FR-17**：系统应实现“按未知类型分流”的处置策略：
  - `multipath`：保留并管理多假设路径，按场景选择解；
  - `out_of_scope`：触发证据/工具补全流程并在预算内自动验证；
  - `ontic_unknowable`：停止重复强验证，转入“价值约束下行动 + 明示不可知边界”。

#### FR-H 时间轴变量与遗忘调度
- **FR-18**：系统应为 `Memory/Experience/Cognition` 对象提供统一时间轴字段：`created_at`、`last_accessed_at`、`last_reinforced_at`、`last_verified_at`、`review_due_at`、`stale_since`、`expires_at`、`next_action_at`。
- **FR-19**：系统应支持“到期驱动调度器”，按 `next_action_at` 拉取待处理对象执行遗忘/复核/降权，避免全量扫描。
- **FR-20**：系统应支持可配置衰减函数（至少包含 `half_life`、`reinforcement_count`、`impact_weight`、`risk_tier` 因子）用于记忆权重更新。
- **FR-21**：系统应实现时间条件状态迁移（如 `supported -> uncertain -> stale_uncertain -> archived`）并支持新证据回升路径（reinstate）。

### 2.6 非功能需求（NFR）

- **NFR-1 可追溯性**：高影响结论 100% 具备来源链与变更链。
- **NFR-2 可解释性**：每次高风险决策可输出决策轨迹（decision trace）。
- **NFR-3 安全性**：对注入/篡改具备检测、隔离、回滚能力。
- **NFR-4 可维护性**：schema 版本演进可兼容迁移。
- **NFR-5 稳定性**：在冲突高发场景不进入长期行动冻结。
- **NFR-6 平衡性**：安全性提升不能以有用性崩塌为代价（双目标约束）。
- **NFR-7 反馈闭环率**：关键事件进入反馈闭环的覆盖率应达到目标阈值（建议 ≥90%）。
- **NFR-8 认知可塑性**：认知规则再验证覆盖率应达到目标阈值，防止长期僵化。
- **NFR-9 自驱有效性**：自驱动作的净收益（质量/效率/风险综合）应持续为正。
- **NFR-10 不确定性透明度**：由 `uncertain` 状态驱动的响应必须显式披露不确定性与当前决策模式。
- **NFR-11 人工介入效率**：不确定性事项的人工升级率应控制在目标阈值内，同时高风险漏升率为 0。
- **NFR-12 未知态分流质量**：`uncertain` 事项的 `unknown_type` 标注完整率应达到目标阈值（建议 ≥95%），且分流策略执行成功率可监控。
- **NFR-13 防空转性**：`ontic_unknowable` 事项不得进入无限验证循环，重复验证次数应有上限并受治理监控。
- **NFR-14 遗忘作业效率**：时间轴驱动遗忘作业默认按到期对象处理（O(k)），不得长期依赖全量扫描（O(N)）作为常态。
- **NFR-15 遗忘质量**：遗忘与降权应保持可逆与可解释；误归档率、误降权率需可监控并受阈值治理。

### 2.7 验证与验收方法（V&V）

| 需求类型 | 主要验证方法 |
|---|---|
| MR | 端到端场景验收（E2E）+ 里程碑评审 |
| CR | 规则审计 + 红队攻击测试 + 回滚演练 |
| FR | 单元测试/集成测试/流程测试 |
| NFR | 指标监控 + 压测 + 运行期审计 |

最低验收基线（本阶段）：
1. 能跑通四层对象最小闭环（Memory→Experience→Cognition→Decision）。
2. 能演示一条伪造记忆注入并成功级联回滚。
3. 能演示一条偏执漂移告警并触发纠偏动作。

### 2.8 需求追踪骨架（Traceability Skeleton）

- `MR-1` <- `CR-1`, `FR-5`, `NFR-2`
- `MR-2` <- `FR-3`, `FR-4`, `FR-15`, `FR-17`, `FR-21`, `NFR-1`
- `MR-3` <- `CR-4`, `CR-10`, `CR-11`, `FR-5`, `FR-6`, `FR-16`, `FR-17`, `NFR-10`, `NFR-12`
- `MR-4` <- `CR-5`, `CR-6`, `FR-7`, `FR-9`, `NFR-11`
- `MR-5` <- `CR-12`, `FR-10`, `FR-18`, `FR-19`, `FR-20`, `FR-21`, `NFR-4`, `NFR-5`, `NFR-14`, `NFR-15`
- `MR-6` <- `CR-8`, `CR-9`, `CR-11`, `CR-12`, `FR-13`, `FR-14`, `FR-16`, `FR-17`, `FR-20`, `NFR-9`, `NFR-11`, `NFR-13`, `NFR-14`
- `MR-7` <- `CR-7`, `FR-11`, `FR-12`, `FR-18`, `NFR-7`, `NFR-8`, `NFR-12`, `NFR-15`

> 后续将把该骨架升级为完整 RTM（Requirements Traceability Matrix）。

### 2.9 当前未决问题（Open Issues）

- OI-1：Experience 状态机的最小状态集合是否采用 5 态还是 7 态？
- OI-2：社会认知 L1-L5 的可信评分是否引入时效衰减函数？
- OI-3：冲动调节阈值（arousal/urgency/cooldown）默认值如何定标？
- OI-4：治理作业的执行责任由系统自动化还是人工触发为主？
- OI-5：探索预算如何分配（按风险级别/按任务域/按时间窗）？
- OI-6：关键事件显著性评分采用规则引擎还是学习模型？
- OI-7：`supported/uncertain/refuted` 的状态迁移阈值如何定标？
- OI-8：`uncertain` 场景的人工升级率目标阈值应设为多少？
- OI-9：`multipath/out_of_scope/ontic_unknowable` 的自动判别规则采用规则引擎还是模型判别？
- OI-10：`ontic_unknowable` 的验证上限与退出条件如何定义，才能避免过早放弃与无限空转？
- OI-11：时间衰减函数参数如何定标（`half_life`、`impact_weight`、`reinforcement_count` 权重）？
- OI-12：`next_action_at` 调度器采用何种实现（优先队列/时间轮/分区扫描）以满足规模与延迟目标？

### 2.10 遗忘机制时间轴变量（Baseline）

| 变量 | 含义 | 作用 |
|---|---|---|
| `created_at` | 创建时间 | 生命周期起点 |
| `last_accessed_at` | 最近被访问时间 | 评估活跃度与短期价值 |
| `last_reinforced_at` | 最近被新证据强化时间 | 决定是否延缓遗忘 |
| `last_verified_at` | 最近核验时间 | 支持可信度维护 |
| `review_due_at` | 下次复核时间 | 触发再验证 |
| `stale_since` | 进入陈旧态时间 | 评估长期降权 |
| `expires_at` | 硬过期时间 | 触发归档/冻结 |
| `uncertainty_ttl` | 未知态时限 | 防止无限挂起 |
| `next_action_at` | 下次调度时间 | 提升遗忘作业效率 |

遗忘评分建议（示意）：

`decay_score = f(age, last_access_gap, reinforcement_count, impact_weight, risk_tier)`

其中：
- `age = now - created_at`
- `last_access_gap = now - last_accessed_at`
- `reinforcement_count` 与 `impact_weight` 抑制过快遗忘
- `risk_tier` 决定最低保留强度与复核优先级

### 2.11 数据契约映射（Schema Draft Mapping）

为避免需求停留在概念层，本项目已建立 schema 草案目录：`../schemas/`。

| 需求域 | 对应草案 |
|---|---|
| 时间轴变量基线（2.10） | `common-temporal.schema.json` |
| 人格层对象 | `persona.schema.json` |
| 记忆层对象 | `memory.schema.json` |
| 经验层对象 | `experience.schema.json` |
| 认知层对象（含未知态） | `cognition.schema.json` |

映射原则：
1. 需求条款优先，schema 跟随需求更新。
2. schema 草案用于评审与约束一致性，不等于最终存储实现。
3. 任何 CR/FR 字段变更必须同步更新相应 schema。

### 2.12 文档整理状态（本轮）

- 已完成 legacy 文档重整与只读归档说明。
- 已建立主规范与讨论记录分离机制。
- 已建立 docs 目录总览：`contents-map.md`。

---

## 3. 版本声明

- 本文档是 **新主规范起点**。
- 历史讨论与细节请参见：`archive/requirements-and-architecture.legacy.md`。
- 下一版将补：系统架构视图、接口契约、状态机图与 RTM 全表。
