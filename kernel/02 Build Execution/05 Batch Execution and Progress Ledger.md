## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/04 Architecture Samples and Dependency Build|Architecture Samples and Dependency Build]].
- Next: [[kernel/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].

## Batch Policy

每个 batch 应是一个可独立验收的小模块，而不是任意数量的文件。

一个 batch 至少完成：

1. Canonical notes。
2. 本批 delta 写出：页面状态、缺口与 next batch 更新经 delta 进入 Coverage Ledger；Progress Ledger 与 `Tools/state/watermark.yaml` 由 integrator 在合并时更新，来源或维护批次把水位线推进值写入 delta 的 `watermark_advance` 字段。

batch 关闭的验收清单以 [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review#Batch Review|12/03 Batch Review]] 为准；批内项在 `merge-ready` 前完成，全局项在串行合并时核验。

批次规模按主导档位分级：S 档 ≤24 页、M 档 ≤10 页、L 档 ≤6 页；混合批按其中最高档的上限执行。24 / 10 / 6 是 kernel defaults；所选 profile 可以在 manifest 中显式覆写，运行时必须加载并记录解析后的上限。

不允许只批量创建文件名和 headings 后把整个 batch 标记完成。

## Concurrent Batches

批次默认可并发执行，上限由 contract 的 `concurrency_cap` 字段控制；`3` 是 kernel default，所选 profile manifest 或 task contract 可显式覆写，运行时必须记录解析后的上限。批次 B 可在其它批次 active 时激活，当且仅当同时满足：

1. B 的页面清单与所有 active 批次的清单不相交；integrator 在激活时按 Coverage `next_batch` 判定。
2. B 不编辑枢纽页，包括 MOC、Overview、共享术语页，以及由 `Runtime Card Provider`、`Expression Layer Entry` 或其它 profile-registered hub roles 绑定的页面。枢纽页同步由 integrator 在该批串行合并完成后、下一批合并开始前作为独立小步执行；该内容编辑动作不属于串行区的确定性动作清单。
3. B 的依赖前置全部位于已合并的批次中，不依赖在途批次的页面。

迁移或重构批次必然编辑枢纽页与跨批页面，不满足并发准入，必须独占执行；迁移批 active 期间不激活其它批次。

写入权分区：并发批次只写三处——自己清单内的页面、自己的 receipts 目录、自己的增量文件 `Machine State/Deltas/<batch>.yaml`，其 schema 见 `Tools/schemas/coverage_delta.template.yaml`。Coverage Ledger、Progress Ledger、Required Queue、Amendment Log 与 watermark 仅 integrator 可写。

关批分为两个阶段：批内工作并行完成后，批次进入 `merge-ready`；批内工作包括写作、`--scope` 自查、复核回执到齐、12/03 批内项完成与 delta 写出。随后 integrator 逐个串行合并，只执行确定性动作与全局核验：经 `Tools/apply_delta.py` 应用 delta、对合并后的完整快照运行 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]]、核验 12/03 全局项、产出 gate receipts 并关闭。每次串行合并只处理一个批次。

串行区已知例外保留显式登记机制，当前登记为空。

控制面始终由 integrator 单线程执行，包括 guidance 处置、queue 修订、contract 变更、标准 adoption、批次激活与合并。停滞报警按批各自计时。

## Source-driven Expansion Batch

从一手或厂商来源、论文、postmortem 或社区讨论扩展知识库时，batch 必须遵循 [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]：来源驱动批次必须完整走 [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] 的全部阶段（Stage 1–10）。

来源 batch 可以产生零个、一个或多个 canonical notes。

## Progress Ledger

超长任务需要单独记录：

- Task state。
- Objective、contract version、scope version、queue revision、active batch revision、exclusions 和 standards version。
- Selected Runtime Card IDs 与 Read Sets、loaded set（`Runtime Card Provider` 解析的 artifacts 与升级回读的 module paths）、版本解析结果和 pending gate 项。
- `minimum_run_until`、`checkpoint_at`、`hard_stop_at`。
- Current phase。
- Active batches（≤ `concurrency_cap`）、merge 队列和 ordered Required Queue。
- Completed files。
- Coverage counts by authoring status and disposition。
- Batch review status。
- Audit snapshot、AuditPlan、receipt register reference、reused / superseded / invalidated receipts、unresolved invalidations 和 systemic expansion。
- Evidence maturity and source review status。
- Link and rendering checks。
- Open questions。
- Known gaps。
- Deferred signals、contested claims 和 superseded conclusions。
- Next dependency。
- Amendment Log、pending guidance 和 last reconciled guidance ID。
- Last accepted checkpoint。
- Terminal Audit status 和 Terminal Proof。

进度以质量状态为准，不以累计创建文件数为准。

Progress Ledger 不能使用 profile-registered hub checkbox 或用户 `learning_status` 计算建设进度。页面写作完成、Expression Layer coverage and readiness、证据成熟度和个人学习进度必须分别汇总。

## Machine-readable Ledger

Progress Ledger 的 canonical 形态为 YAML，schema 见 `Tools/schemas/progress_ledger.template.yaml`，只允许模板头注释声明的受限子集语法。markdown 散文视图可选、由 YAML 派生，不作为对账依据。恢复任务时直接加载 YAML Ledger（连同 Coverage Ledger），而不是重读散文 checkpoint。
