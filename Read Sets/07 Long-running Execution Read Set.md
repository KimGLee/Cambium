## Purpose

用于需要多个 batch、持续时间约束、checkpoint、resume、Coverage Ledger 或 Terminal Proof 的长任务。

## Start

先读取 [[Knowledge Base Standards/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]，再读取：

- [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[Knowledge Base Standards/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[Knowledge Base Standards/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]]
- [[Knowledge Base Standards/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]]
- [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff|Completion and Handoff]]
- [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]

同时组合实际内容类型对应的 authoring、source、interview 或 migration Read Set。

## Triggered

- 收到中途指导、范围变化、纠正或优先级变化：读取 [[Knowledge Base Standards/02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]]。
- 用户 guidance 同时包含技术 hypothesis 或 source lead：读取 [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]]。
- 关闭 guidance amendment：读取 [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review|Guidance Source and Interview Review]]。
- 新 source-driven batch：读取 [[kernel/06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]]。

## Gate

每个 batch 使用 [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]，并按 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] 生成、复用或失效验证证据；任务完成候选必须组合 [[Knowledge Base Standards/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]。

## Related

- [[Knowledge Base Standards/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Build Execution]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance]]
