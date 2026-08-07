---
type: read-set
route_id: R01
---

## Purpose

Core Bootstrap is the minimal common read set for all Knowledge Base Standards tasks. It provides only control boundaries; it contains no concrete authoring, source, migration, or QA methods.

## Start

Read in order:

1. [[kernel/K00 Standards Overview|Standards Overview]]
2. [[kernel/K00 Standards Control/03 Standards Governance#Standards Control|Standards Control]]
3. [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]
4. [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]]
5. [[kernel/K00 Standards Control/04 Control State and Scope|Control State and Scope]]
6. [[kernel/K00 Standards Control/05 Core Principles|Core Principles]]
7. [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]]

Then select the task-specific Read Set from the [[kernel/Read Sets/Read Sets Index|Read Sets Index]].

## Required Decisions

- Make the objective, scope, exclusions, and the user's latest instructions explicit.
- Apply the [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate|Runtime Startup Gate]]: inspect the repository root for `.cambium/` before any content or state
  write. If it exists, run `python3 Tools/check_queue.py . --resume-status`
  and reconcile the recorded task and exact `next_action`; never infer a fresh
  start from a new Agent context. If it is absent, only a selected persistent,
  resumable, or multi-batch route may initialize it.
- Confirm whether the current task is authorized to modify `Knowledge Base Standards` or protected directories.
- Confirm that canonical ownership, factual correctness, and protection of user modifications still take precedence.
- Distinguish task completion, authoring status, the registered `Expression Status Axis`, evidence maturity, and learning status.
- Confirm that the active Standards state is instantiated and its one `selected_profile_manifest` resolves to a filled profile that passed `check_profile.py`. While any placeholder remains, a content task cannot freeze its contract and MUST stop before execution.
- Record the current Standards version, exact selected profile manifest path, and actual loaded set: selected Rxx route IDs and Runtime Card paths, any combined namespaced profile route, and every Read Set or leaf path actually read back.

## Not Sufficient For

Core Bootstrap alone does not authorize starting the following work:

- Canonical note authoring.
- Source promotion.
- Expression Layer migration.
- Folder refactor.
- Large-scale creation, moves, or deletion.
- Long-running batch execution.
- Completion or Terminal Audit.

This work MUST proceed by loading the corresponding Read Set. Large-scale creation, moves, or deletion additionally passes [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]] alongside that route.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K00 Standards Overview|Standards Overview]]
