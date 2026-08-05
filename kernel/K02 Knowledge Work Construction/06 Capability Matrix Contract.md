## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|Global Map Contract]].
- Next: [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|Gap Register Contract]].

## Purpose And Ownership

This module is the sole kernel owner of the exact record contract for the
`Capability Matrix`. K02/03 owns its applicability, lifecycle, and
reconciliation. K02/04 owns its runtime, audit, deterministic-check, receipt,
and affected-path boundaries. The selected profile supplies its path, scale,
and pass authority; it does not redefine the record format below.

## Capability Matrix Contract

The `Capability Matrix` states what the corpus enables an operator or consuming
agent to explain, design, execute, verify, diagnose, or recover. Its
restricted-YAML document has exactly `schema_version: 1` and `capabilities`.
Each capability record has exactly `capability_id`, `capability`, `priority`,
`map_entry_ids`, `canonical_markdown_paths`, `current_level`, `target_level`,
`evidence_paths`, and `gap_ids`. The four multi-value fields are explicit YAML
lists, including when empty. `priority` is exactly `P0`, `P1`, or `P2`.

`current_level` and `target_level` come from the selected profile's declared
scale, whose explicit integer rank is contiguous from `0` and orders values
from lowest to highest. A target value has `target_eligible: true`; current
values may use any registered scale row. Every canonical
path shares a Profile Scope directory with at least one linked Map Entry; a
leaf owner does not become a global navigation entry merely because the Matrix
uses it. A capability below target names at least one Gap ID, and each
Matrix/Gap link is bidirectional.

A capability passes only when its current rank is at least its target rank,
the target scale row is eligible, and a current
`corpus-plan-semantic-acceptance` receipt records `accepted` for that exact
Capability ID under the role and decision scope bound by the selected Profile.
K02/04 owns that receipt's machine contract and invalidation boundary. The
decision concerns semantic capability coverage; it does not change page
`authoring_status`, `coverage_disposition`, batch lifecycle, task state, or
evidence maturity. The matrix MUST be reconciled when its owner paths,
prerequisites, capability definitions, scale evidence, or target values change.

Matrix `priority` ranks a corpus capability only. It does not grant or change a
page's P0/P1/P2 priority, alter Coverage, consume quota, or override the
selected Profile's `Priority Rubric`; page priority remains owned by that
rubric and the kernel quota contract.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
