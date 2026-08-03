---
type: runtime-card
route_id: R11
read_set: kernel/Read Sets/R11 Large-scale Work Admission Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/R11 Large-scale Work Admission Read Set.md
  - kernel/K00 Standards Control/02 Task Routing and Pre-execution.md
  - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/K02 Build Execution/01 Contract Time and Task State.md
  - kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
source_hash: c135c89b2b35
---
# R11 Large-scale Work Admission Card

> Compiled kernel guidance. This Card packages the existing large-scale Pre-execution Gate and authorizes no content operation by itself.

## Use When

Load before large-scale creation, moves, or deletion, together with [[kernel/Cards/R01 Core Bootstrap Card|R01 Core Bootstrap]] and the Card for the actual work. Ordinary local work does not load R11.

## Admission Checklist

- [ ] Record contract, scope, queue, initial batch, Standards version, selected routes and Cards, actual source read-backs, target scope, exclusions, and latest user requirements.
- [ ] Make `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate explicit; leave unspecified fields explicitly empty.
- [ ] Create or refresh the Coverage Ledger and reconcile it with the file system and exclusions.
- [ ] Inventory ownership, incoming links, user modifications, and the Required Queue.
- [ ] Identify foundational dependencies without burying shared foundations in the profile application mainline.
- [ ] For source-driven work, establish a source inventory and claim-extraction plan.
- [ ] Define batch acceptance, `rendering_mode`, deterministic checks, and the objective trigger plus unresolved question for any visual escalation.
- [ ] Load the latest Audit Receipt Register. Do not build an AuditPlan at task start; build it exactly once before batch close.
- [ ] Load the task-specific Card and resolve all triggered and future Gate modules.

## Gate

Execution may begin only when every applicable admission item is resolved. If authority, ownership, scope, source evidence, a required dependency, or a recovery boundary remains unresolved, stay in planning or investigation.

## Read Back When

Read [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|R11 Read Set]] and the canonical owner for complete Task Contract fields, Coverage reconciliation, time semantics, receipt planning, or visual escalation. Add R07 only for multi-batch, checkpoint, or resume behavior.
