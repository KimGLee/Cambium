## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Next: [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]].

## Purpose And Boundary

This module classifies common task intents into stable Route IDs. It owns only
the shared meaning of those classifications and the choice of Route ID. It does
not define Card selection, Read Set membership, loading order, phase mapping,
delivery, or execution behavior. Those relationships remain with their
respective component owners.

## Task Classification Table

| Task intent | Route ID | Classification boundary |
|---|---|---|
| Create or make a targeted extension to one knowledge page, including a terminology or rendering correction confined to that page | `R02` | one canonical page is the primary governed unit |
| Create a process page, system page, or complete knowledge module | `R03` | placement, dependencies, navigation, and module completeness must be decided together |
| Extend knowledge from external source material | `R04` | claims must be admitted, reconciled, and promoted from identified sources |
| Build a source-grounded industry Case Study | `R04 + R02` | source intake and single-page authorship are both primary dimensions |
| Create, migrate, or review expression-layer content | `R05` | the primary object is an expression artifact rather than canonical knowledge alone |
| Bulk rename, move, split, merge, or restructure governed content | `R06` | the operation changes existing ownership, paths, or graph structure |
| Start, resume, pause, or complete a long-running task | `R07 + <work route>` | persistent task execution is combined with the route describing the governed work |
| Enter build-completion acceptance or Terminal Audit | `R08 + <work route>` | completion must be proved for the route that produced the governed result; maintenance completion does not use `R08` |
| Modify Standards or another Cambium control-plane component | `R09` | the task changes governance authority, contracts, or component structure |
| Perform a bounded periodic freshness or maintenance run | `R10 + <work route>` | the run is budget-bounded maintenance applied to objects selected by a governed work route |
| Admit large-scale creation, movement, or deletion to execution | `R11 + <work route>` | large-scale work requires a separate admission classification before its work route executes |
| Run a targeted or specialized audit | `R12 + <subject route>` | the audit is bounded by a specific finding, risk, sample, or subject area |
| Create or reconcile the corpus map, capability coverage, or semantic-gap register | `R13` | the output is corpus-planning state rather than knowledge-content execution |

Route combination records multiple independent task dimensions; it does not
merge their meanings or transfer responsibility between their owners. If no
row describes the task without stretching its classification boundary, the
task requires an explicit routing decision rather than an inferred nearest
match.
