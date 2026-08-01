## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Next: [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment|Mid-task Guidance and Amendment]].

## Purpose

本标准规定超长知识库建设任务如何规划、执行、验证和恢复，防止一次性铺设大量空壳页面、后期失去一致性或中断后重复工作。

本文件只管理“建设知识库的长任务”，不定义部署运行主体自身如何执行长任务。所选知识主线中的 long-horizon reliability、checkpoint、context continuity 和 execution recovery，由所选 profile 注册的 `Profile Scope` 提供具体角色与 canonical knowledge 路由。

## Core Execution Principle

```text
Architecture before expansion.
Canonical ownership before writing.
Foundations before unsupported system claims.
Evidence before canonical promotion.
Representative samples before bulk migration.
Complete batches before claiming progress.
Verification after every batch.
Time boundaries are not completion evidence.
Every in-scope page must have an explicit disposition.
```

## Phase 0: Freeze The Contract

正式执行前确认：

- 目标岗位和知识边界。
- 所选 `Profile Scope` 注册的组织主线，以及基础知识必须完整保留的约束。
- 排除范围。
- 顶层目录和 ownership。
- Note type、depth、metadata 和语言规范。
- 所选 `Expression Layer Entry` 注册的表达产物拆分方式。
- Sources、图表和质量门槛。
- Source-to-knowledge intake、evidence maturity 和 canonical promotion 方式。
- Contract version、scope version、queue revision、initial batch revision 和 Standards version。
- 并发批次上限 `concurrency_cap`（kernel 默认值为 `3`；所选 profile manifest 或 task contract 可显式覆写）；批次并发准入与合并规则见 [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches。
- Selected Runtime Card IDs 与 Read Sets、实际 loaded set（`Runtime Card Provider` 解析的 artifacts 与升级回读的 module paths）、triggered 项和尚未执行的 gate 项。
- 允许修改 scope、priority、batch 和 Standards 的 authority。
- `minimum_run_until`、`checkpoint_at`、`hard_stop_at` 和 Completion Gate。
- Pause、cancel、block 和 resume 的处理方式。
- Mid-task guidance 的记录、acknowledgement、safe switching 和 amendment policy。
- Required、optional、deferred 和 excluded coverage 的判定方式。

标准未确认前，不进行大规模迁移。

任务开始后冻结 `standards_version`。内容建设过程中不得顺手修改 Standards；只有用户明确授权的 governance change 才能修改。Standards 变更后必须提升版本，并按修订记录的 changed-predicate 清单执行 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] Active-task Adoption（清单为空即 no-op）。

## Time And Stop Semantics

时间字段必须使用明确语义，不能统一写成含义模糊的“截止时间”：

- `minimum_run_until`：在此时间前不得主动停止。达到该时间只解除最早停止限制，不表示任务完成。
- `checkpoint_at`：在该时间记录进度、重新验证计划或向用户汇报；任务默认继续。
- `hard_stop_at`：到达该时间必须停止执行并写入 checkpoint。若 Completion Gate 未通过，状态必须是 `paused`，不能写成 `complete`。
- `completion_gate`：与时间无关的质量和覆盖条件，定义真正完成需要哪些证据。

当用户说“某时间之前不允许停止”时，必须记录为 `minimum_run_until`。当用户说“某时间停止”时，才记录为 `hard_stop_at`。语义不明确时必须在大规模执行前解决歧义。

没有 `hard_stop_at` 时，任务持续到 Completion Gate 通过、用户暂停或取消、或者出现真实 blocker。达到 `minimum_run_until` 后仍有 Required gaps 时必须继续。

## Task State Machine

长任务状态只记录在 task Progress Ledger，不使用知识页的 `authoring_status` 表达：

```text
planned
 -> active
 -> completion-candidate
 -> complete

active <-> paused
active <-> blocked
completion-candidate -> active
planned / active / paused / blocked / completion-candidate -> cancelled
```

- `planned`：contract、scope 或 inventory 尚未满足执行门槛。
- `active`：正在执行或已经确定下一 Required batch。
- `paused`：任务未完成，但因用户要求、`hard_stop_at`、运行中断或显式 checkpoint 暂停；必须保存恢复信息。
- `blocked`：存在无法在当前环境中解决的外部依赖，且没有其它 Required work 可以推进。
- `completion-candidate`：执行者认为范围已满足，等待 Terminal Audit。
- `complete`：Terminal Audit 产生有效 Terminal Proof。
- `cancelled`：用户明确终止当前 contract；不代表知识范围完成。

`paused`、`blocked`、`cancelled` 和 `complete` 必须区分。运行环境结束、没有正在编辑的文件、达到时间点或 `In-progress batch: None` 都不能自动产生 `complete`。
