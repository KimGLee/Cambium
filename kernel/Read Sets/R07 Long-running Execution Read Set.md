---
type: read-set
route_id: R07
---

## Purpose

Used for persistent, resumable, or multi-batch tasks requiring sustained time constraints, checkpoints, the Coverage Ledger, Required Queue, or the completion path selected by the Task Contract.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]]
- [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace|Runtime State Model and Namespace]]
- [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]]
- [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|Task State and Transition Rules]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover|Interruption Recovery and Rollover]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]

Also combine the authoring, source, `Expression Layer`, or migration Read Set matching the actual content type.

When the task also meets the large-scale creation, move, or deletion predicate, it MUST first pass [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]]. R07 owns sustained execution, checkpointing, and resume; it does not replace that admission gate.

## Triggered

- Mid-task guidance, scope change, correction, or priority change received: read [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]], [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]], and [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]].
- User guidance also contains a technical hypothesis or source lead: read [[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads|User Guidance Hypotheses and Source Leads]].
- Closing a guidance amendment: read [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].
- New source-driven batch: read [[kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy|Evidence Maturity and Batch Policy]].
- Batch activation finds the current Standards version differs from the contract-frozen one: read [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Gate

Each batch uses [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]], and generates, reuses, or invalidates verification evidence per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]. Every writer first passes the [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate|Runtime Startup Gate]] loaded through R01; an existing namespace is inspected with `check_queue.py --resume-status` and never overwritten, while an absent namespace is initialized only for persistent, resumable, or multi-batch work. Activation consumes `--require-ready`; at serial merge the integrator runs [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]] and consumes a current Queue receipt before close. A build task entering `completion-candidate` MUST combine [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]. A maintenance task never enters that state; a persistent R10 run instead consumes the bounded gate in [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings#Completion Gates|K13/12]].

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction]]
- [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
