---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/04 Source-driven Expansion Read Set.md
  - 06 Knowledge Intake and Evolution/01 Intake Scope and Knowledge Model.md
  - 06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline.md
  - 06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles.md
  - 06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy.md
  - 06 Knowledge Intake and Evolution/06 Intake Anti-patterns and Acceptance.md
  - 07 Sources and Accuracy/03 Official and Cross-source Verification.md
  - 08 Metadata and Status/04 Evidence and Relationship Metadata.md
source_hash: 1588b0b19e4d
---
# 04 Source-driven Expansion Card（来源驱动扩展卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

- Source≠Claim≠Object≠File；many-to-many，禁按文章标题建 note。
- 用户 lead/hypothesis/一手经历：先读 06/02 定证据角色。
- 环境扫描按水位线增量（Tools/state/watermark.yaml），批次关闭时推进。

## During（执行中）

Pipeline 10 阶段（跳过记 deferral）：
1 Scanning：记发现/guidance ID；热度≠promotion
2 Capture：identity/authority/边界/未证明；仅复用来源建 SN
3 Claims：四标签 Reported/Inference/Synthesis/Recommendation
4 Evidence：七角色（06/03）
5 Synthesis：术语同指/条件可比/vendor 边界
6 Gap：缺失问题/机制，非缺某文
7 Graph Decision：十动作各给理由（06/03）
8 Creation：同步 ownership/links/MOC/metadata
9 Promotion gate（见下）
10 Supersession：保留替代关系

六值（08/04）：signal 信号 | single-source 单源 | corroborated 多独立源 | validated 实验/复现/生产 | contested 冲突 | superseded 被取代。

官方来源三句：①官方文章＝一手 implementation evidence，只证其公开系统、不证行业规律；②未披露组件不得常识补全；③P0/P1 前沿对照 OpenAI/Anthropic 一手资料，缺则如实记录。

骨架（06/04）—SN：Identity/Problem/Context/Key Claims/Evidence/Assumptions/Limitations/Not Established/Affected Notes/Open Questions；RS：Question/Source Set/Terminology Mapping/Agreements/Disagreements/Evidence Comparison/Generalizable/Vendor-specific/Unresolved/Graph Changes。

反模式：①按标题建 note；②官方文章≠行业事实；③每 URL 一文件；④无 claim provenance；⑤推翻后静默改写。

## Gate（关闭前）

Promotion gate：
- [ ] 对象有问题/边界/owner；已查同义页
- [ ] claims 可溯源、四类已分；范围/厂商条件已说明
- [ ] 语气配 maturity；达 depth class 非空壳
- [ ] check_links、check_vocab `--scope 本页` 自查（不产 receipt）

批次：10 阶段走全；guidance→graph change 沿 ID 追踪；未过 gate 不标 canonical；批级 gate＝Batch-close Closed List（12/07，七项，含 check_vocab 全库）。

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 用户 lead | [[Knowledge Base Standards/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads\|06/02]] |
| 指标数字 | [[Knowledge Base Standards/07 Sources and Accuracy/04 Evaluation and Source Quality\|07/04]] |
| 时效/公式 | [[Knowledge Base Standards/07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty\|07/05]] |
| 写 note | [[Knowledge Base Standards/Read Sets/02 Single Note Authoring Read Set\|RS 02]] |
| promotion | [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review\|12/04]] |
