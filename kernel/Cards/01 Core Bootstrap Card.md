---
type: runtime-card
card_id: kernel-01
read_set: kernel/Read Sets/01 Core Bootstrap Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/01 Core Bootstrap Read Set.md
  - kernel/00 Standards Overview.md
  - kernel/00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/00 Standards Control/02 Task Routing and Pre-execution.md
  - kernel/00 Standards Control/04 Control State and Scope.md
  - kernel/00 Standards Control/05 Core Principles.md
  - kernel/00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/00 Standards Control/07 Effort Tiering and Priority Quota.md
source_hash: cd6961151eba
---
# Core Bootstrap Card

> Compiled kernel guidance. Do not hand-edit. When this Card is incomplete or disputed, read its `source_files`; source text wins.

## Use When

Load this Card for every task, then combine the task Card selected in [[kernel/Cards/00 Card Index|Card Index]]. Core Bootstrap alone never authorizes authoring, source promotion, migration, long-running execution, or completion.

## Shared Tiering

| Tier | Determination | Acceptance ceremony |
|---|---|---|
| S | `priority=P2`, terminology stub, placeholder, or link-aggregation page | Deterministic checks; no separate note gate; sampled at batch close |
| M | Regular `priority=P1` page | Deterministic checks plus the canonical M-tier checklist compiled in `kernel-02`; folded into Batch Review |
| L | `priority=P0`, a kernel-listed mainline type, or a profile-registered L trigger | Full 12/01 review, standalone note gate, and applicable expression checks |

The selected profile's `Priority Rubric` grants P0/P1. Record the tier in the Coverage Ledger and escalate one tier when disputed.

## Before Start

- [ ] State the objective, target scope, exclusions, and latest user instructions.
- [ ] Confirm modification authority, especially for the Standards and other protected paths.
- [ ] Inventory existing ownership, incoming links, user modifications, and the Required Queue; do not overwrite changes of unknown origin.
- [ ] Resolve the task Card, triggered modules, future Gate modules, selected profile slots, and any profile extension route.
- [ ] Record Standards version, Card IDs and paths, Read Sets actually read back, contract, queue, initial batch, and loaded set.
- [ ] Make `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate explicit; leave unspecified fields explicitly empty.
- [ ] Create or refresh the Coverage Ledger and reconcile it with the file system and exclusions.
- [ ] Identify foundational dependencies; do not bury shared foundations inside a profile application mainline.
- [ ] For source work, establish a source inventory and claim-extraction plan.
- [ ] Define batch acceptance, `rendering_mode`, deterministic checks, and any objective visual escalation trigger; load the Audit Receipt Register but build the AuditPlan only before batch close.

## During

- Preserve canonical ownership, factual correctness, safety, and user modifications under the kernel precedence rules.
- Keep task state, authoring status, expression status, evidence maturity, and learning status independent.
- Load only the task modules needed by the current event or gate. A long task does not justify loading entire domains.
- Re-resolve the loaded set after a Standards, scope, or route change.
- Do not infer completion from elapsed time, file count, structural checks, or an empty active batch.

## Gate

Large-scale creation, moves, or deletion may begin only when every Before Start item is satisfied and the task-specific Card is loaded. If authority, ownership, scope, source evidence, or a required dependency is unresolved, stop at planning or investigation.

## Read Back When

Read the canonical sources for a precedence conflict, a complete Task Contract, protected-scope interpretation, an unlisted task state transition, a disputed tier, or any case the selected task Card does not cover.
