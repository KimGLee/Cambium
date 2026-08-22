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
  - kernel/K00 Standards Control/15 Read Set Loading Boundaries.md
  - kernel/K00 Standards Control/17 Profile Dependency Closure.md
  - kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery.md
  - kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate.md
  - kernel/K13 Task Runtime and Execution Control/21 Phased Reading Plan.md
  - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
readback_sources: []
readback_policy: none
source_hash: '3550fde7adbb'
compiled_source_hash: '3550fde7adbb'
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
| L | `priority=P0`, a core concept / process-flow / system / risk-control mainline page, or a profile-registered L trigger | Full K12/01 review, standalone note gate, and applicable expression checks |

The selected profile's `Priority Rubric` grants P0/P1. Record the tier in the Coverage Ledger and escalate one tier when disputed.

## Before Start

- [ ] Enter through a `card-first-phased-readback-v4` admission result. It
  freezes every phase's piece manifest and the environment that resolved it;
  the bytes arrive afterwards one phase part per tool result, each
  acknowledged from this execution context. Admission records `host-bound` or
  `prepared` and claims no delivery of its own.
- [ ] Pull the `batch-preflight` phase before working, and each later phase
  before the act that owes it: the gate phase before the first judgment or
  merge-ready request, the governance phase before a batch that edits the
  control plane can reach merge-ready. Treat a phase as incomplete until its
  ack set matches that phase's frozen manifest. An unbound CLI delivery, or
  any unregistered adapter, is `degraded`: work may proceed, but no layer may
  claim machine-enforced Card delivery.
- [ ] State the objective, target scope, exclusions, and latest user instructions.
- [ ] Inspect the repository root for `.cambium/state/` before any content or
  task-state write. If it exists, run `python3 Tools/check_queue.py . --resume-status`,
  reconcile the recorded task and exact `next_action`, and do not initialize a
  replacement. If task state is absent, only a selected persistent, resumable,
  or multi-batch route may initialize it beside any valid governance/history
  already under `.cambium/`.
- [ ] Confirm the active Standards state is instantiated and its one selected
  profile manifest has a current passing `profile-load` result. That result
  must bind the Profile directory snapshot and typed dependency-closure
  fingerprint; a filled manifest or a slot-only check is not load authority.
  If a placeholder or Profile-owned edge remains unresolved, stop before
  freezing a content task. Governance may continue only to adopt a passing
  after Profile.
- [ ] Confirm modification authority, especially for the Standards and other protected paths.
- [ ] Do not roll back, overwrite, or delete user modifications whose origin cannot be confirmed. A large-scale task additionally inventories ownership, incoming links, and user modifications in the target scope under R11.
- [ ] Resolve the task Card, triggered modules, future Gate modules, selected profile slots, and any profile extension route.
- [ ] Freeze Standards version, exact `selected_profile_manifest`, selected route/Card paths, and the derived Read Set / leaf delivery boundary. Delivery belongs to the activation/read-back receipt chain. Keep Profile closure dependencies in `profile-load`, not `loaded_module_paths`.
- [ ] Keep the prerequisite chain continuous; foundational knowledge is not deleted, compressed, or reduced to an empty shell for the application mainline. A large-scale task additionally identifies foundational dependencies under R11.
- [ ] If the task is large-scale creation, moves, or deletion, load and pass [[kernel/Cards/R11 Large-scale Work Admission Card|R11 Large-scale Work Admission]] before execution.

## During

- Preserve canonical ownership, factual correctness, safety, and user modifications under the kernel precedence rules.
- Keep task state, authoring status, expression status, evidence maturity, and learning status independent.
- Load only the task modules needed by the current event or gate. A long task does not justify loading entire domains.
- Re-resolve the loaded set after a Standards, scope, or route change.
- Never hand-edit canonical runtime state; use the writer that owns the
  affected control edge.
- Do not infer completion from elapsed time, file count, structural checks, or a Queue-derived view with no `open` batch.

## Gate

Routine work may begin only when this common boundary and the task-specific Card are resolved. Large-scale creation, moves, or deletion additionally requires R11. If the Standards state, authority, ownership, scope, or a required dependency is unresolved, stop at planning or investigation.

## Read Back When

Read the canonical sources for a precedence conflict, a complete Task Contract, protected-scope interpretation, an unlisted task state transition, a disputed tier, or any case the selected task Card does not cover.
