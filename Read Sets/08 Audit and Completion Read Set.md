## Purpose

用于审查内容、关闭 batch 或 module，以及执行 Completion Gate、Terminal Audit 和最终报告。

## Start

先读取：

- [[Knowledge Base Standards/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]
- 与被审 finding 相关的 Read Sets。
- [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[Knowledge Base Standards/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[Knowledge Base Standards/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]
- [[Knowledge Base Standards/02 Build Execution/07 Completion and Handoff|Completion and Handoff]]
- [[profiles/agent-atlas/language-contract|Language Contract]]

## Triggered

- 图、表格、公式、图片、embed 或具体显示问题：读取 [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification|Rendering Verification]]。先审计 Level 0 / Level 1 确定性证据；只在存在记录的 visual exception trigger 时审计 UI、截图或录屏证据。
- Guidance、source promotion 或 Interview content：读取 [[Knowledge Base Standards/12 Quality Assurance/04 Guidance Source and Interview Review|Guidance Source and Interview Review]]。
- 目录迁移：读取 [[Knowledge Base Standards/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]] 的 Gate modules。

## Completion Rule

不能因为通过结构检查就跳过 correctness、depth、provenance、integration 或适用的 deterministic rendering。审计先根据 AuditReceipt、fingerprint 和 invalidation event 生成范围：最终图相关检查按 Batch-close Closed List（12/07）执行，昂贵人工审阅覆盖 changed、invalidated、overdue 和抽样对象。Terminal Audit 只能审计已经满足全部适用 gate 的 completion candidate；没有 visual exception trigger 时，不得把缺少 UI、截图或录屏证据判为失败。

## Related

- [[Knowledge Base Standards/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance]]
