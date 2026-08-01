## Purpose

用于周期性知识库更新与保鲜（Maintenance Run）：在声明的预算封套内消化 `check_freshness` 过期清单、水位线增量、`needs_rereview` 传播标记与 candidates 池，并以有界的 Maintenance completion 语义关闭本轮。

## Start

先读取 [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]，再读取：

- [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]（Maintenance Run Envelope 与 Effort Tiering）
- [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]（Freshness And Review Due）
- [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]]（Stage 1 的增量扫描与水位线语义）
- [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]]
- [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]

开工前必须声明预算封套（N 页、N 批次或 N 小时，三选一），并从四个来源合并候选清单：过期复验清单 ∪ 水位线增量 ∪ `needs_rereview` 标记 ∪ candidates 池（duplicate / vocab / language）。候选连续 3 个维护轮未被预算选中自动降级为 log-only，再次被新扫描命中时重新入池；维护轮开始时输出 deferred 年龄分布，滞留超过 3 轮的项必须显式处置。以上规则 owner 为 [[Knowledge Base Standards/00 Standards Control/02 Task Routing and Pre-execution|00/02]] Maintenance Run Envelope，此处为执行摘要。

## Triggered

- 收到 `needs_rereview` 项：读取 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Content-level Propagation|Content-level Propagation]]。
- 出现退役或合并候选：读取 [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]。
- 本轮产出 L 档页面：读取 [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review#Substantive Correctness Review|Substantive Correctness Review]]。
- 涉及来源驱动内容：组合 [[kernel/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]。
- 涉及 Expression Layer 内容：组合所选 profile 通过 `Routing And Gate Registry` 登记的 `Expression Layer Read Set`。

## Gate

- 批次关闭：[[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]。
- 本轮清单关闭：[[Knowledge Base Standards/00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]]——有界完成语义：封套内候选清单关闭＋Ledger 与水位线推进＋各批次过适用 QA gates 即完成；不适用全库 Terminal Proof，被截掉的 deferred 项移交下一轮维护，不构成缺口。

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance]]
