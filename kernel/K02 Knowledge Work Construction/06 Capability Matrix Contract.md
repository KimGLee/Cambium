## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]].
- Next: [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|Gap Register Contract]].

## Purpose And Ownership

This module owns the cross-instance meaning and invariants of the `Capability Matrix`. Its closed record shape is owned by the registered `capability-matrix` machine contract. K02/03 owns applicability, lifecycle, and reconciliation; K02/04 owns audit and evidence-currentness boundaries. The selected Profile binds the instance path, scale, and pass authority.

## Capability Matrix Contract

The `Capability Matrix` states what the corpus enables an operator or consuming agent to explain, design, execute, verify, diagnose, or recover. The `capability-matrix` machine contract is the sole normative source for record fields, closed values, cardinality, and serialization. This module does not repeat that contract in prose.

Every capability has a stable identity, a priority, one or more owning Map Entries and canonical owners, current and target levels, evidence bindings, and any unresolved Gap bindings. Map and canonical-owner bindings are never empty. Gap and evidence bindings may be empty only where the machine contract and the semantic rules below allow it.

`current_level` and `target_level` come from the selected profile's declared scale, whose explicit integer rank is contiguous from `0` and orders values from lowest to highest. A target value has `target_eligible: true`; current values may use any registered scale row. Every canonical path shares a Profile Scope directory with at least one linked Map Entry; a leaf owner does not become a global navigation entry merely because the Matrix uses it. A capability below target names at least one Gap ID, and each Matrix/Gap link is bidirectional. A capability whose `current_level` is any scale row above rank `0` MUST name at least one evidence path; only a capability still at rank `0`, the scale's lowest row, leaves `evidence_paths` empty.

A capability passes only when its current rank is at least its target rank, the target scale row is eligible, and a current `corpus-plan-semantic-acceptance` receipt records `accepted` for that exact Capability ID under the role and decision scope bound by the selected Profile. K02/04 owns that receipt's machine contract and invalidation boundary. The decision concerns semantic capability coverage; it does not change page `authoring_status`, `coverage_disposition`, batch lifecycle, task state, or evidence maturity. The matrix MUST be reconciled when its owner paths, prerequisites, capability definitions, scale evidence, or target values change.

Matrix `priority` ranks a corpus capability only. It does not grant or change a page's P0/P1/P2 priority, alter Coverage, activate or satisfy an optional quota, or override the selected Profile's `Priority Rubric`; page priority and any numeric guardrail remain owned by that rubric under K00/07.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
