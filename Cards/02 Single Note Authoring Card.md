---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/02 Single Note Authoring Read Set.md
  - 03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - 04 Content Depth/01 Depth Model and Foundation.md
  - 04 Content Depth/02 Core Concept Structure.md
  - 04 Content Depth/03 Process and Flow Structure.md
  - 04 Content Depth/04 System and Production Reasoning.md
  - 05 Terminology/03 Naming Context and Linking.md
  - 07 Sources and Accuracy/02 Claims Sources and Classification.md
  - 08 Metadata and Status/01 Frontmatter and Core Vocabularies.md
  - 08 Metadata and Status/03 Status Axes.md
  - 09 Wiki Link and Navigation/01 Link Semantics and Body Links.md
  - 09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - 10 Writing and Formatting/05 Chinese-first Technical Language.md
  - 12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
  - 12 Quality Assurance/05 Automated and Manual Checks.md
source_hash: e47d014dd25e
---
# 02 Single Note Authoring Card（单页写作卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- 定 note type＋唯一 owner；有同义页则扩写。
- Frontmatter 必填（词表见 08 域）：type/domain/scope/level/depth/priority/authoring_status/interview_status/coverage_disposition/volatility/lifecycle（review_by 脚本生成，不手填）；deferred 须 deferred_reason＋next_batch。

## During（执行中）

- core concept：问题>定义>直觉>机制>公式/示例>假设>适用边界>权衡>失败>调试>比较>生产/评估>Sources
- process-flow：目标/退出>角色 authority（model/harness/executor/human）>输入/前置>happy path>分支/循环>状态>外部效果>retry/timeout>失败恢复>终止证明>worked/failure trace
- system：目标/非目标>需求>架构>组件>端到端>状态/并发>失败/恢复>安全>观测>扩展/成本>替代；P0/P1 答五链路 execution/state/coordination/evidence/recovery

语言三规则：①中文解释，英文只保 identity；②只写 `English（中文）`；③文件名纯英文，英文标题加中文注释。
链接三规则：①首次有意义出现建链＋语境；②重要依赖入正文非仅 Related；③歧义用完整路径，表内 pipe 转义 `\|`。
Sources：Core/System 页必有 `## Sources`；关键/时效 claim 就近放链接，语气配证据（四标签 07/02）。

## Gate（关闭前）

L 档：成稿＋自查即触发独立复核（干净上下文 subagent；主线不得代产 receipt），与写作并行；关批仅需回执到齐。

- [ ] check_links、check_vocab `--scope 本页` 自查（不产 receipt）；批级 gate＝Batch-close Closed List（12/07，七项，含 check_vocab 全库）
- [ ] 原因链成立；例子说明机制；Failure Mode 五要素 trigger/symptom/cause/detection/mitigation
- [ ] 无残留 Interview Answer/自测，只留 Card link
- [ ] 深度＝问题覆盖（按 type）；基础页可独立学习
- [ ] 渲染止于 Level 0/1；视觉升级须有 trigger

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 术语拆页 | [[Knowledge Base Standards/05 Terminology/01 Terminology Extraction\|05/01]] |
| 指标 | [[Knowledge Base Standards/07 Sources and Accuracy/04 Evaluation and Source Quality\|07/04]] |
| 数学/表格/代码 | [[Knowledge Base Standards/10 Writing and Formatting/02 Mathematics Tables and Code\|10/02]] |
| 图/资产 | [[Knowledge Base Standards/10 Writing and Formatting/03 Diagrams and Assets\|10/03]] |
| 显示问题 | [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification\|12/02]] |
