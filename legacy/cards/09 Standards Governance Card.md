---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/09 Standards Governance Read Set.md
  - 00 Standards Control/01 Operating Role and Reading Protocol.md
  - 00 Standards Control/02 Task Routing and Pre-execution.md
  - 00 Standards Control/03 Standards Governance.md
  - 00 Standards Control/05 Core Principles and Standards Map.md
  - 00 Standards Control/07 v1.1 to v1.2 Migration Map.md
  - 02 Build Execution/02 Mid-task Guidance and Amendment.md
  - 12 Quality Assurance/05 Automated and Manual Checks.md
  - 12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
source_hash: 8bd49244239d
---
# 09 Standards Governance Card（标准治理卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。Governance 任务必须通读原文，本卡仅作导航与流程备忘，不可作为修订依据。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。Governance 任务本身按 L 档处理。

## Before Start（开工前）

- 用户必须明确授权 governance change；普通内容任务不得隐式进入 RS 09。
- 通读 RS 09 Start 列表全部原文（00 域六模块＋00/07＋02/02＋09/03＋10/05＋12/05）。
- 变更前冻结：Standards version、受影响模块、incoming links、active task impact。

## During（执行中）

修订流程五步（00/03）：①确认是 governance change 而非内容编辑；②记录受影响 Standards 与原因；③提升 standards_version；④更新 00 的 routing 与 Change Summary（修订者必须列出 changed-predicate 清单，列空即声明 no-op）；⑤按 changed-predicate 清单执行 12/07 Active-task Adoption——清单为空即 no-op，字节 diff＋一行 adoption receipt 即完成。

- 结构迁移必须建立旧块→新 owner 完整映射；拆分不得缩减、摘要或静默删除规则（00/07）。
- Revision Write-back Checklist 位置清单（00/03，回写未完成不得关闭）：00/04 状态表；00 Overview 的 Protected Defaults 与 Task Router；相关 domain MOC 的 Module Index；相关 Read Set target 列表；Cross-domain Rule Registry（00/05）；重新生成受影响 Runtime Cards 与 Tools/vocab.yaml；关闭前 `stamp_cards.py --check` 必须通过。
- Owner 唯一性：每条规则只有一个 canonical owner；Registry（00/05）中对象只改 owner 文件，其它位置只准 wiki link 引用。
- 重复检测跑法：`python3 Tools/duplicate_check.py .`（可加 `--scope 子路径`）——段落级相似度候选，人工按 Registry 判定。默认全库，仅 governance 与维护轮调用；批次与单页不再调用。

## Gate（关闭前）

- [ ] 按 12/03 验证目录、MOC 与 coverage；链接完整性由批次关闭的 Batch-close Closed List（12/07，语义定义仍在 09/05）覆盖
- [ ] 按 12/07 记录受影响 active task 的 receipt compatibility、失效范围与 adoption plan；旧证据不满足新 schema 标 legacy-evidence，不伪造 fingerprint
- [ ] Write-back Checklist 全部回写（含 Cards 与 vocab.yaml 重新生成）
- [ ] 涉及 rendering policy 时按 12/02 记录实际级别；用 12/06 关闭 governance task

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 结构迁移先例与映射 | [[Knowledge Base Standards/00 Standards Control/07 v1.1 to v1.2 Migration Map\|00/07]] |
| Registry 与 owner 判定 | [[Knowledge Base Standards/00 Standards Control/05 Core Principles and Standards Map\|00/05]] |
| guidance 记录与授权 | [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment\|02/02]] |
| 语言政策 | [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language\|10/05]] |
