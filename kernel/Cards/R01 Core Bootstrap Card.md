---
type: runtime-card
route_id: R01
read_set: kernel/Read Sets/R01 Core Bootstrap Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R01 Core Bootstrap Read Set.md
  - kernel/K00 Standards Overview.md
  - kernel/K00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/K00 Standards Control/02 Task Routing.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K00 Standards Control/03 Standards Governance.md
  - kernel/K00 Standards Control/04 Control State and Scope.md
  - kernel/K00 Standards Control/05 Core Principles.md
  - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
source_hash: '1ee7ad654395'
---
# R01 Core Bootstrap Card

> Compiled kernel guidance. Do not hand-edit. When this Card is incomplete or disputed, read its `source_files`; source text wins.

## Use When

Load this Card for every task, then combine the task Card selected in [[kernel/Cards/Card Index|Card Index]]. Core Bootstrap alone never authorizes authoring, source promotion, migration, long-running execution, or completion.

## Shared Tiering

| Tier | Determination | Acceptance ceremony |
|---|---|---|
| S | `priority=P2`, terminology stub, placeholder, or link-aggregation page | Deterministic checks; no separate note gate; sampled at batch close |
| M | Regular `priority=P1` page | Deterministic checks plus the canonical M-tier checklist compiled in `R02`; folded into Batch Review |
| L | `priority=P0`, a kernel-listed mainline type, or a profile-registered L trigger | Full K12/01 review, standalone note gate, and applicable expression checks |

The selected profile's `Priority Rubric` grants P0/P1. Record the tier in the Coverage Ledger and escalate one tier when disputed.

## Before Start

- [ ] State the objective, target scope, exclusions, and latest user instructions.
- [ ] Inspect the repository root for `.cambium/` before any content or state
  write. If it exists, run `python3 Tools/check_queue.py . --resume-status`,
  reconcile the recorded task and exact `next_action`, and do not initialize a
  replacement. If it is absent, only a selected persistent, resumable, or
  multi-batch route may initialize it.
- [ ] Confirm the active Standards state is instantiated and its one selected profile manifest resolves to a filled, checked profile. If a placeholder remains, stop before freezing a content task.
- [ ] Confirm modification authority, especially for the Standards and other protected paths.
- [ ] Inspect existing ownership, incoming links, and user modifications in the target scope; do not overwrite changes of unknown origin.
- [ ] Resolve the task Card, triggered modules, future Gate modules, selected profile slots, and any profile extension route.
- [ ] Record Standards version, exact `selected_profile_manifest`, selected Rxx route IDs and Runtime Card paths, and every Read Set or leaf path actually read back.
- [ ] Identify foundational dependencies; do not bury shared foundations inside a profile application mainline.
- [ ] If the task is large-scale creation, moves, or deletion, load and pass [[kernel/Cards/R11 Large-scale Work Admission Card|R11 Large-scale Work Admission]] before execution.

## During

- Preserve canonical ownership, factual correctness, safety, and user modifications under the kernel precedence rules.
- Keep task state, authoring status, expression status, evidence maturity, and learning status independent.
- Load only the task modules needed by the current event or gate. A long task does not justify loading entire domains.
- Re-resolve the loaded set after a Standards, scope, or route change.
- Do not infer completion from elapsed time, file count, structural checks, or a Queue-derived view with no `open` batch.

## Gate

Routine work may begin only when this common boundary and the task-specific Card are resolved. Large-scale creation, moves, or deletion additionally requires R11. If the Standards state, authority, ownership, scope, or a required dependency is unresolved, stop at planning or investigation.

## Read Back When

Read the canonical sources for a precedence conflict, a complete Task Contract, protected-scope interpretation, an unlisted task state transition, a disputed tier, or any case the selected task Card does not cover.
