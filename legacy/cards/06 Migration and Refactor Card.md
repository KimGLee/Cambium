---
type: runtime-card
compiled_from: v2.3
source_files:
  - Read Sets/06 Migration and Refactor Read Set.md
  - 00 Standards Control/07 v1.1 to v1.2 Migration Map.md
  - 01 Scope and Architecture/03 Foundation Preservation.md
  - 01 Scope and Architecture/04 Folder and Shared Ownership.md
  - 02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - 02 Build Execution/06 Existing Changes Migration and Resume.md
  - 03 Note Types and Ownership/03 Split and Duplication Policy.md
  - 08 Metadata and Status/05 Review Source and Migration Metadata.md
  - 09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - 11 Interview Content/07 Migration Audit and Acceptance.md
source_hash: 7cfc9489690d
---
# 06 Migration and Refactor Card（迁移与重构卡）

> 本卡为编译产物，禁止手改；标准修订后用治理流程重新生成。规则争议以 source_files 原文为准。

## Tiering（分档）

| 档 | 判定 | 仪式 |
|---|---|---|
| S | priority=P2，或术语存根/占位/链接聚合页 | 仅脚本检查；无 note gate；批次关闭时按 12/03 抽查 |
| M | priority=P1 常规页面 | 脚本检查＋本卡 Gate 清单；note gate 并入 batch gate |
| L | priority=P0，或 core concept / process-flow / system / risk-control 主线页、System Deep Dive、Interview Card 集 | 完整流程：12/01 全量 review＋独立 note gate＋interview 迁移核对 |

争议时上调一档。分档规则 owner：[[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]]。

## Before Start（开工前）

迁移不变量：
- 基础保全：不得为突出 Agent/Harness 删除或压缩基础页（01/03）。
- 内容守恒：拆分/迁移逐块映射，不得缩减、摘要或静默删除；禁止先删后补（02/06、00/07）。
- 现有修改默认属用户；不回滚无关改动、不做 destructive reset（02/06）。

Physical Folder Policy 五条件（01/04，全过才可动目录）：①新 ownership 明确；②incoming links 已盘点；③新路径无同名歧义；④Overview/Roadmap/graph group 可同步；⑤迁移后全库链接检查。禁止无知识收益的批量移动。

开工前建清单：source path、target path、incoming links、heading anchors、content owner、rollback boundary。迁移批独占执行，不与其它批次并发（02/05）。

## During（执行中）

Migration Safety 七步（02/06，顺序不可倒）：识别 canonical target > 盘点出入链 > 建并验证新页 > 更新引用 > 确认完整迁移 > 才删旧文件/重复 > 链接验证由批次封闭清单（12/07）覆盖。

- 旧→新映射登记：每个原内容块在且仅在一个新 owner（00/07）；heading links 改到 canonical target；确认重复后合并义务优先（03/03）；仅物理删除文件需 governance 授权。
- Interview 内容：先建完整 Card 并过链接检查，再删旧答案，原位留 Card link（11/07）。
- 拆分判定按 03/03；owner 同时变化读 03/02。
- 退役/合并按 03/03：tombstone＋`lifecycle: retired`＋入链改指 gate。
- Metadata：旧 status 只迁 authoring_status；无 frontmatter 页默认 unassessed；迁移不改正文语义（08/05）。
- Resume：中断前置 paused/blocked＋checkpoint（含修改文件与下一精确动作）；恢复从双 Ledger 与文件状态恢复，核对目标/契约/用户新修改后才回 active（02/06）。

## Gate（关闭前）

- [ ] check_links `--scope 涉及页` 自查（不产 receipt）：missing=0、ambiguous=0，无重命名错误 heading links；批级 gate＝封闭清单（12/07，七项，含 check_vocab 全库）
- [ ] 内容守恒对账：旧块→新 owner 映射完整，无缩减、遗漏或重复 owner
- [ ] 新文件有合理 incoming link；Overview/Roadmap/Interview Card/graph group 已同步
- [ ] 删除旧文件前已确认新页面完整且引用已更新
- [ ] Coverage Ledger 重新对账；Batch Review 按 12/03

## Escalation（例外跳转）

| 情形 | 读原文 |
|---|---|
| 多批次迁移 | [[Knowledge Base Standards/Read Sets/07 Long-running Execution Read Set\|RS 07]] |
| owner 同时变化 | [[Knowledge Base Standards/03 Note Types and Ownership/02 Ownership and Canonical Notes\|03/02]] |
| Standards 结构迁移 | [[Knowledge Base Standards/Read Sets/09 Standards Governance Read Set\|RS 09]] |
