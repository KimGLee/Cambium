## Navigation

- Parent: [[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]].
- Previous: [[Knowledge Base Standards/00 Standards Control/04 Control State and Scope|Control State and Scope]].
- Next: [[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].

## Core Principles

1. One canonical source：一个概念只在一个 canonical note 中完整维护。
2. Separation of concerns：知识、术语、系统设计、案例和面试表达各自承担不同职责。
3. Depth over volume：以问题是否讲透为标准，不以文件数和字数为标准。
4. Explain the why：不仅解释是什么，还要解释为什么存在、为什么这样设计和朴素方案为什么失败。
5. Reusable knowledge：共享定义通过 wiki links 复用，不在不同页面复制。
6. Local readability：引用外部术语后，当前段落仍应能独立理解。
7. Evidence first：关键事实、公式、协议和时效性内容必须有可靠来源。
8. Foundations remain complete：以 Agent/Harness 为中心不代表删除或压缩基础知识。
9. Source-to-knowledge：外部来源先经过 claim extraction、综合和归属判断，再改变 canonical knowledge。
10. Interview separation：面试话术和题库放在独立 `Interview Preparation` 体系。
11. No empty completion：空壳页面、占位链接和只有两三句的核心页面不算完成。
12. Continuous verification：每批内容都要执行链接、公式、渲染、来源、重复性和覆盖度检查。
13. State separation：任务、写作、面试、证据和学习状态不能互相替代。
14. Durable coverage：每个 in-scope 页面和 Required knowledge object 都有 Coverage Ledger disposition。
15. Time is not proof：最早运行时间、checkpoint 和 hard stop 都不能代替 Completion Gate。
16. Deterministic-first rendering：全量检查源文件，静态 compile / parse 按内容触发；UI、截图和视觉模型只在确定性证据无法消除具体显示不确定性时使用；录屏只用于静态证据无法表达的时序或交互问题。
17. Guidance is durable：中途用户引导进入 Amendment Log，不能只保留在临时对话上下文中。
18. Authority is not evidence：用户决定当前任务要做什么；技术 claim 是否成立仍由来源和验证决定。
19. Incremental amendment：新 guidance 只修改明确涉及的 contract 维度，未冲突约束继续有效。
20. Modular ownership：每条规则在一个 leaf module 中拥有 canonical owner，领域 MOC 只负责路由。
21. Deterministic loading：通过 Read Set、trigger 和 gate 解析需要读取的模块，不能临时猜测，也不要求整域全量读取。
22. Content conservation：Standards 拆分和迁移必须逐块映射；未经单独授权不得借结构调整缩减、摘要或删除规则。
23. Chinese-first technical language：中文承担解释，英文保持技术 identity；文件名只用英文，双语标题和首次术语只使用 `English（中文）`。

## Standards Map

- `Read Sets` [[Knowledge Base Standards/Read Sets/00 Read Sets Index|Read Sets Index]]：按任务、事件和执行阶段组合需要读取的 leaf modules。
- `01` [[kernel/01 Scope and Architecture Standard|Scope and Architecture Standard]]：范围、Agent/Harness 主线、基础层和 logical architecture。
- `02` [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]：长任务 contract、Mid-task Guidance、时间语义、task state、Coverage Ledger、batch、恢复和 Terminal Proof。
- `03` [[kernel/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]：note types、Process / Flow、canonical ownership、split 和 duplication。
- `04` [[kernel/04 Content Depth Standard|Content Depth Standard]]：Atomic / Core / System 深度、Process / Flow、系统链路和 evaluation provenance。
- `05` [[kernel/05 Terminology Standard|Terminology Standard]]：专有名词提取、aliases、复用和 emerging terminology。
- `06` [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]：用户 hypothesis / source lead、source-to-knowledge pipeline、synthesis、graph impact 和 promotion。
- `07` [[kernel/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]：来源角色、claim、公式、指标和时效性核验。
- `08` [[kernel/08 Metadata and Status Standard|Metadata and Status Standard]]：type、domain、priority、authoring / interview / learning status、coverage disposition 和 evidence maturity。
- `09` [[Knowledge Base Standards/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]：正文链接、结构导航、path、alias 和验证。
- `10` [[Knowledge Base Standards/10 Writing and Formatting Standard|Writing and Formatting Standard]]：英文文件名、中文优先技术表达、`English（中文）` 显示合同、公式、表格、图方向、图完整性和 rendering workflow。
- `11` [[Knowledge Base Standards/11 Interview Content Standard|Interview Content Standard]]：Interview Cards、coverage status、双语回答、系统深挖和 migration audit。
- `12` [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance Standard]]：单篇、batch、Guidance / Coverage reconciliation、模块、source promotion、面试、分层渲染和 Terminal Audit。

## Cross-domain Rule Registry

以下高危对象在全库只有唯一 canonical owner。修改这些对象只能修改 owner 文件；其它任何位置只允许通过 Wiki Link 引用，不允许复制内容（无论是否略有改写）。

| 对象 | Canonical owner |
|---|---|
| Terminal Proof 公式 | [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff|Completion and Handoff]] |
| Terminal Audit 流程与 Proof 字段清单 | [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]] |
| `task_state` 词表 | [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]] |
| authoring / interview / learning 状态词表 | [[kernel/08 Metadata and Status/03 Status Axes|Status Axes]] |
| `evidence_maturity` 定义 | [[kernel/08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]] |
| Evidence roles | [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Source Note / Research Synthesis 模板 | [[kernel/06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]] |
| Evaluation provenance 要素清单 | [[kernel/07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]] |
| 官方来源政策 | [[kernel/07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]] |
| 语言政策 | [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|Chinese-first Technical Language]] |
| Interview 双语政策 | [[Knowledge Base Standards/11 Interview Content/04 System Deep Dive and Bilingual Policy|System Deep Dive and Bilingual Policy]] |
| System Deep Dive 骨架 | [[Knowledge Base Standards/11 Interview Content/04 System Deep Dive and Bilingual Policy|System Deep Dive and Bilingual Policy]] |
| Batch / Coverage 验收清单 | [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]] |
| Source-to-Knowledge pipeline | [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| 保质期与 volatility 词表 | [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] |
| 退役与合并流程 | [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]] |
| 维护轮预算封套 | [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]] |

## Control Registry

Cross-domain Rule Registry 管内容规则“规则住在哪”；本控制注册表管控制义务“检查发生在哪”。每个风险对象有且只有一个 canonical gate，其它层只验证凭证存在且未失效，不重新检查。

| 风险对象 | Canonical gate（唯一） | 其它层的行为 |
|---|---|---|
| Wiki 链接完整性 | 批次关闭：[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|封闭清单]] check_links 产 receipt | note 关闭仅本页 `--scope` 自查；迁移/退役仅定向改指；终审验证最后批次 receipt，不重跑 |
| Frontmatter 词表 | 批次关闭：[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|封闭清单]]第 7 项 check_vocab 产 receipt | note 关闭 `--scope` 自查；终审信任 receipt |
| 并发写冲突 | 批次激活时：integrator 按 Coverage `next_batch` 执行清单相交性检查（[[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches） | 并发批次仅写自身清单页面、receipts 目录与 delta 文件；全局状态文件 integrator 专属 |
| 内容正确性（人工） | note 关闭：[[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] 按档位审阅 | 批级人工审范围 = changed ∪ invalidated ∪ 抽样；P0 长期保障由 freshness 复验承担；终审验证 receipts＋有界抽样 |
| Coverage 对账 | 批次关闭仅 file-count（封闭清单第 4 项）；问题清单按 [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|12/03]] 在模块完成与 completion-candidate 前执行 | inventory 后与 scope/guidance 变化时各一次；批次开始不对账；completion-candidate 前与终审步骤 4 合并 |
| 标准版本一致性 | 批次激活自动版本自检：[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Active-task Adoption|Active-task Adoption]] | 有 delta 走增量 adoption；无 delta 一行 receipt；终审 check_proof 校验 |
| Guidance 处置 | intake 一次完整处置：[[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment|02/02]]（门槛为重要 Guidance） | 批关闭仅对 `last_reconciled_guidance_id` 后增量对账；终审只读账验证 disposition |
| 凭证有效性 | 批次关闭前 AuditPlan 一次：[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] | 批次开始只加载 Receipt Register；Reuse Gate 条件保留 |
| 渲染 | note 关闭 Level 0/1：[[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification|12/02]] | 批关闭枚举检查一项；终审信任 receipt |
| Interview 迁移扫描 | 批次关闭：[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|封闭清单]]第 6 项＋changed-scope 扫描 | 其它层引用封闭清单，不另做全库扫描 |
| 重复检测 | 维护轮与 governance 任务：[[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|12/05]] duplicate_check | 批次层面仅封闭清单 basename 级；段落级扫描不每批跑 |
| 知识时效 | 维护轮开始 check_freshness：[[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|08/05]] | 不在批次自动检查清单中 |
