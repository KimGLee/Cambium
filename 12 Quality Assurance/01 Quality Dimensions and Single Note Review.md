## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Next: [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification|Rendering Verification]].

## Purpose

本标准定义单篇笔记、模块和全库的验收方式。文件创建完成、测试脚本通过或字数足够，都不能单独代表知识完成。

## Quality Dimensions

每项内容从以下维度验收：

- Coverage：应该回答的问题是否覆盖。
- Correctness：事实、公式和术语是否准确。
- Depth：是否解释原因、机制、假设和失败。
- Structure：章节是否有逻辑承接。
- Language clarity：中文解释是否完整，英文 identity 是否精确，双语显示是否统一为 `English（中文）`。
- Reuse：专有名词是否 canonicalize。
- Integration：正文和上级入口是否正确链接。
- Application：是否有例子、评估和工程考虑。
- Provenance：关键 claims、指标和案例是否能追溯到证据与测量过程。
- Evidence maturity：正文语气是否符合 signal、corroborated、validated 或 contested 状态。
- Interview readiness：是否有独立 Interview Card。
- Maintainability：来源、元数据和 ownership 是否明确。
- Rendering：Markdown、公式、表格和图片是否正常。

## Single Note Review

适用范围：本节全量清单适用于 L 档页面；M 档页面按对应 Runtime Card 的 Gate 清单验收并并入 batch gate；S 档页面仅做确定性脚本检查，批次关闭时抽样复核（分档规则见 [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|分档规则]]）。

### Structure

- Note type 明确。
- 开头说明主题位置或要解决的问题。
- 章节顺序符合从问题到机制再到应用和失败的逻辑。
- 没有重复标题、日期或无意义元信息。

### Content

- 不只有定义和列表。
- 关键机制有解释，不只陈述结果。
- 重要假设和边界已说明。
- 至少有适合该 note type 的例子。
- Failure Mode 包含 trigger、symptom、cause、detection、mitigation。
- 术语解释没有不必要地挤占当前主题。
- 语言维度按 [[profiles/agent-atlas/language-contract#Acceptance And Audit（验收与审计）|Language Contract / Acceptance And Audit]] 验收。高频错误提示：双语标题与首次术语必须写成 `English（中文）`，不得写反向 `中文（English）`；正文用完整中文句子承担解释，不用英文关键词堆叠代替推理。
- 基础知识页能够独立解释其学科机制，没有被压缩成 Agent 使用说明。
- System 页面覆盖 execution、state、coordination、evidence 和 recovery paths。

### Accuracy

- 公式、符号和数值例子已检查。
- 时效性事实已验证。
- Sources 能直接支撑关键结论。
- 没有把经验性建议写成绝对事实。
- Reported claim、inference、cross-source synthesis 和 recommendation 已区分。
- 指标能够追溯到 task、dataset、trial、Harness、grader 和 aggregation。

### Links

- Parent、prerequisites 和关键依赖可导航。
- 正文第一次有意义出现的术语已链接。
- Related 不是唯一引用位置。
- Interview Card link 已按优先级建立。
- Source Note、Research Synthesis、canonical note 和 Case Study 之间的关系可导航。
- 没有 unresolved 或 ambiguous link。

### Rendering

- 数学公式正常显示。
- 表格列没有被 wiki alias pipe 破坏。
- 图片路径和尺寸可用。
- 代码块有正确 fence 和语言。
- Mermaid、SVG、embed 和 callout 按实际使用方式可读。
- 图表完整表达知识结构，没有为了适配视口删除关键节点、分支或失败路径。

Rendering pass 只能证明展示层满足要求，不能证明 Coverage、Correctness、Depth 或 Provenance。

## Substantive Correctness Review

L 档页面强制执行实质正确性复核；S / M 档不强制，由批次抽查覆盖。

执行方式：由独立执行上下文执行——以干净上下文启动、不携带作者上下文的 subagent 或新会话，输入仅为笔记正文及其 Sources，即满足独立性。主线程不得自行产出复核 receipt；receipt 须标注复核者的执行上下文标识。复核在页面成稿（drafted 且通过 `--scope` 自查）时即可触发，与后续页面写作并行；批次关闭仅要求复核回执到齐。复核内容：

- 重推关键推理链，确认结论确实由前提得出。
- 抽查 2–3 个关键 claim，对照来源原文核对。
- 检查"来源没说这么强"的过度引申。

复核产出 receipt（`check: substantive_review`，schema 同 `Tools/schemas/receipt.template.jsonl`）。

触发时机：

- 页面新建时。
- 页面被标记 `needs_rereview` 时。
- `review_by` 过期复验时。

审查对象与收敛规则：

- 复核判定的是**文档级正确性**——推理链是否成立、claim 是否有来源支撑、是否过度引申；不判定所描述系统、协议或设计在对抗环境下是否无懈可击。设计类内容的已知弱点、未决攻击面与工程取舍，如实记入该页 Limitations / Open Questions 即视为正确陈述，不构成复核失败。
- Findings 三级分级：`critical`（结论错误、推理不成立、claim 与来源矛盾）必须修复；`major`（过度引申、缺关键限定）修复或降级措辞；`minor`（表述改进）记录即可，不阻断。仅 critical / major 阻断关闭。
- 轮次上限为 2：第 1 轮复核产出分级 findings；修复后第 2 轮**只确认第 1 轮 findings 是否关闭，不得引入新的审查范围**。确认轮新发现的问题记入 Open Questions 或标记 `needs_rereview` 交由维护轮消化，不重开本轮复核。
- 两轮后仍无法关闭，或复核范围在轮间持续扩张，必须升级用户裁决，不得自行续轮。

存量豁免：触发时机以上述三种情形为限。Standards 版本升级本身不触发存量页面的补做——已处于 `reviewed`、`review_by` 未过期且未被标记 `needs_rereview` 的页面，不因标准变更重开实质正确性复核；标准变更导致的 receipts 失效仅要求按 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] 重跑确定性检查，不等于重开人工复核。
