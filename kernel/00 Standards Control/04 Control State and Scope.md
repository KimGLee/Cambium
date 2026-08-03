## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].
- Next: [[kernel/00 Standards Control/05 Core Principles|Core Principles]].

## Control State Separation

| State | Owner | Meaning | Must Not Be Used As |
|---|---|---|---|
| `task_state` | Progress Ledger | planned, active, paused, blocked, completion-candidate, complete, cancelled | page content quality |
| `authoring_status` | Coverage Ledger / page metadata | unassessed, outline, drafted, reviewed | user learning progress or evidence strength |
| `Expression Status Axis` | Selected profile registry | expression-artifact coverage and readiness values registered by the selected profile | canonical note depth |
| `evidence_maturity` | Canonical / Source / Synthesis note | signal, single-source, corroborated, validated, contested, superseded | whether writing is complete |
| `learning_status` | User learning workflow | not-started, learning, self-tested, mastered | knowledge-base build progress |

This table is a control-plane quick view; the complete vocabularies are authoritative at each owner: for task_state see [[kernel/02 Build Execution/01 Contract Time and Task State|02/01]], for the remaining kernel axes see [[kernel/08 Metadata and Status/03 Status Axes|08/03]], and expression status values are provided by the `Expression Status Axis` role.

`coverage_disposition` additionally states whether a page is required, optional, deferred, or excluded in the current scope.

## Scope

This Standard applies to the knowledge-corpus scope explicitly registered by the selected `Profile Scope` and governed by this control plane. The specific goals, knowledge structure, content catalog, and expansion scope are provided by that role; the kernel does not hard-code a deployment inventory.

Explicit exclusions MUST be written into the `Excluded Scope` slot; when no exclusions are registered, that slot MUST still be explicitly empty. Migration, refactoring, or acceptance MUST NOT go beyond the current task contract and that slot; any scope change requires corresponding authorization.

Kernel Standards belong to the control plane and do not count as ordinary content-building output. Only a separately authorized governance task MAY modify them; ordinary content tasks MUST treat them as a read-only protected scope.
