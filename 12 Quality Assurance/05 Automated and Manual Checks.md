## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review|Guidance Source and Interview Review]].
- Next: [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]].

## Automated Checks

每批任务按 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 在批次关闭前生成 AuditPlan。批次关闭的全量检查以 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] 的 Batch-close Closed List 为准，本页不另行开列。

## Domain-specific Checks

以下领域专项检查项仅对 changed / invalidated scope 运行：

- `unclassified_guidance`、`accepted_unmapped_guidance` 和 `implemented_unverified_guidance` 检查。
- `unassessed`、没有 next batch 的 Required gaps 和无理由 deferred/excluded 检查。
- 空文件、极短 core/process/system 文件检查；结果只作为审阅候选，不自动判失败。
- 缺失 Sources、Related、metadata 和 Interview link 检查——其中 frontmatter 受控词表校验已实现为 `Tools/check_vocab.py`（词表取自 `Tools/vocab.yaml`，编译产物）；其批次关闭的全库运行为封闭清单第 7 项（[[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]），本处仅 changed-scope 自查。
- 语言自动检查按 [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|10/05]] 的 Acceptance And Audit 清单执行；高频项：reader-facing 英文-only heading candidates 与反向 `中文（English）` 双语格式检查、文件夹或 Markdown 文件名中的中文字符检查——语言候选检测已实现为 `Tools/check_language.py`（只产生候选，永不直接判失败）。
- Source Note 缺失 source URL、date、evidence role 或 affected notes 检查。
- Research Synthesis 缺失 source set、disagreement 或 graph decision 检查。
- `evidence_maturity` 与 source-driven 页面类型一致性检查。
- Standards domain MOC、leaf module 和 Read Set target 一致性检查——MOC Module Index 与实际 H2 headings 的一致性已实现为 `Tools/check_moc.py`（只产生候选）；维护轮与 governance 任务运行，不在批次检查中运行。
- Standards migration 中原 content block 的 owner 唯一性、遗漏和重复检查。
- Task Contract 中 selected Cards 与 Read Sets、loaded set 和 Standards version 的可解析性检查。
- Mermaid compile、asset path、deterministic rendering evidence 和 `rendering_mode` 枚举检查。
- Level 2–4 记录必须包含 visual trigger、unresolved question、target 和 result；没有 trigger 的 batch 不要求 visual evidence。
- 跨文件重复块检测——用 `Tools/duplicate_check.py` 跑段落级相似度扫描，相似段落对报为候选，人工判定是否违反 [[Knowledge Base Standards/00 Standards Control/05 Core Principles and Standards Map#Cross-domain Rule Registry|Cross-domain Rule Registry]]。仅维护轮与 governance 任务运行；批次层面仅保留封闭清单中的 basename 级检测。
- Terminal Proof 完整性与零值条件校验（canonical 定义见 [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]]）——已实现为 `Tools/check_proof.py`，可与 Coverage Ledger 交叉对账。
- 知识时效检查——`Tools/check_freshness.py` 按 volatility 与 last_verified 计算 review_by，输出过期清单（按 priority 排序），作为维护轮候选输入。维护轮专属，不在批次检查中运行。规则 owner 见 [[Knowledge Base Standards/08 Metadata and Status/05 Review Source and Migration Metadata|08/05]]。

语言相关自动检查只能产生候选项，不能按字符比例自动判失败（定义与例外边界见 [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|10/05]]）。自动检查只能发现结构问题，不能代替内容审阅。

## Manual Checks

人工或模型审阅覆盖 changed、invalidated 与有界抽样对象；不得只因进入下一审计层就无差别重做所有已通过页面。P0/P1 页面不因优先级常驻人工审范围，其长期保障由 freshness 到期复验承担。需要判断：

- 原因链是否成立。
- 例子是否真的说明机制。
- 比较维度是否公平。
- 失败模式是否具体。
- 内容是否存在重复或空洞扩写。
- 页面是否能经受进一步追问。
- 当前主题是否仍然聚焦。
- 语言维度按 [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|10/05]] 的 Acceptance And Audit 验收；高频项：中文是否真正承担了解释而非机械翻译、双语标题与首次术语是否统一为 `English（中文）`。
- 外部来源是否真正改变或补强知识，而不是只增加摘要文件。
- Agent/Harness 中心与基础知识完整性是否同时成立。
- Process / Flow 页面是否包含 decision、branch、loop、state mutation、external effect、failure 和 terminal condition。
- 视觉升级是否确实来自确定性证据无法消除的具体显示不确定性，而不是因为新增了一种视觉构造就默认打开 UI。
- Level 2–4 是否只检查解决 unresolved question 所需的最小页面、区域、viewport 或动作序列；无 trigger 时是否正确停止在 Level 0 / Level 1。
- UI、截图或录屏是否被错误用于证明正文、链接、公式语义、来源或 coverage。
- User guidance 是否被正确理解、限界和排期，而不是被遗漏、过度扩张或降级。
- Guidance 导致的中断是否发生在安全边界，是否保留可恢复 checkpoint。

每项人工结论必须绑定具体 scope、rubric/acceptance predicate、artifact/dependency fingerprints 和 evidence reference。抽样发现可重复问题时，必须先定义受影响 family，再按有界范围扩大，不能静默把局部失败留给 Terminal Audit。
