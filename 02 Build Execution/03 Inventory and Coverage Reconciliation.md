## Navigation

- Parent: [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]].
- Next: [[Knowledge Base Standards/02 Build Execution/04 Architecture Samples and Dependency Build|Architecture Samples and Dependency Build]].

## Phase 1: Inventory

对现有知识库建立 inventory：

- File path。
- Note type。
- Domain。
- Depth class。
- Priority。
- Canonical owner。
- Authoring status。
- Interview status。
- Coverage disposition。
- Missing sections。
- Existing aliases and incoming links。
- Interview content migration target。
- Source type and evidence maturity，适用于来源驱动页面。
- Existing Source Notes、Research Synthesis 和 unsupported claims。
- Rendering mode：`source-only`、`deterministic-static`、`targeted-visual-exception`、`expanded-ui` 或 `temporal-recording`；后三者必须关联客观 trigger 和 unresolved question。
- Deferred reason、re-entry condition 和 next batch。
- Originating guidance IDs 和 amendment version。
- Last audited、last reviewed 和 last verified。
- 各质量维度最新有效 `receipt_id`、artifact/dependency fingerprint、review due 和 invalidation state；旧任务无法重建时标记 `legacy-evidence`。

Inventory 必须排除 `Python Algorithm Agent Training`。

Inventory 必须形成持久化、可查询的 Coverage Ledger，不能只存在于临时分析或执行者记忆中。Coverage Ledger 可以按领域拆分，但必须有一个汇总入口，并满足：

- 每个 in-scope Markdown 文件恰好有一个记录。
- 尚未创建但属于 Required coverage 的知识对象同样有记录。
- 文件系统数量、排除范围和 Ledger 汇总数量可以对账。
- 没有 metadata 的旧页面默认为 `authoring_status: unassessed`，不能因文件存在而视为 drafted。
- 每个未完成的 Required 项都有明确 `next_batch`。
- `deferred` 和 `excluded` 都有原因与重新进入条件或 scope 依据。

Coverage Ledger 是 page-level coverage 的权威记录；Progress Ledger 只记录 task 和 batch 进度。

## Coverage Reconciliation

Coverage reconciliation 至少在以下时点执行：

1. Phase 1 inventory 完成后。
2. 每个 batch 串行合并关闭后（此时仅执行 file-count 对账，即封闭清单第 4 项）。
3. Scope 或 Standards version 变化后。
4. Accepted guidance 改变 coverage 或 priority 后。
5. 任务进入 `completion-candidate` 前。

Reconciliation 只重新计算受文件、scope、Guidance 或 Standards 变化影响的 receipt validity；不能因为一次无关修改让所有内容审阅日期失效，也不能把 `last_reviewed` 当作仍有效的证明。最终图状态相关的 file count、link 和 control-plane invariants仍按 gate 全量计算。

对账检查问题清单以 [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|12/03]] 的 Coverage Reconciliation Review 为准。

行数、文件存在和 link resolution 只用于发现候选异常，不能代替 note-type-aware 内容审阅。

## Machine-readable Ledger

Coverage Ledger 的 canonical 形态为 YAML，schema 见 `Tools/schemas/coverage_ledger.template.yaml`，只允许模板头注释声明的受限子集语法。markdown 散文视图可选、由 YAML 派生，不作为对账依据；对账和 Terminal Audit 只认 YAML 形态。恢复任务时直接加载 YAML Ledger，而不是重读散文视图。
