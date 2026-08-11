## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract|Gate Receipt Payload Contract]].
- Next: [[kernel/K12 Quality Assurance/19 Incremental Audit Planning|Incremental Audit Planning]].

## Purpose

[[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|K12/08]] files the judgment items whose audit object is one page. This module files the layers above it — Batch, Module, Specialized, Terminal — and the receipt dimension of each Control Registry Gate stating no judgment item of its own, a value its receipt otherwise lacks. `Terms`, `Evidence Role`, and `Profile Registration` stay with K12/08; the halves are read together.

## Item Map

| Section | Items | Role | Dimension |
|---|---|---|---|
| `K12/04 Guidance Reconciliation Review` | all 11 | emits | guidance_and_contract |
| `K12/04 Source Intake And Promotion Review` | all 9 | emits | source_and_currentness |
| `K12/03 Module` | Overview reflects real structure; duplicate canonical notes; orphans; Standards ownership and Read Set reciprocity | emits | structure_and_links |
| `K12/03 Module` | unexplained P0 / P1 concepts; prerequisite chain continuous; `Profile Scope` mainline and foundation | emits | coverage_and_integration |
| `K12/03 Module` | Case Study usable; depth balance, core not thinner than peripheral | emits | content_and_depth |
| `K12/03 Module` | new external sources went through gap analysis | emits | source_and_currentness |
| `K12/03 Module` | R05 artifact synchronization across the module | emits | guidance_and_contract |
| `K11/01` | canonical/expression responsibility separation | emits | content_and_depth |
| `K11/02` | readiness-axis independence | emits | guidance_and_contract |
| `K11/04` | evidence qualification is preserved in expression | emits | source_and_currentness |
| `K11/05` | resolvable bidirectional canonical bindings | emits | structure_and_links |
| `K11/07` | migration conservation of content and bindings | emits | coverage_and_integration |
| `K12/03 Coverage` | the other nine of its ten items (was eight) | emits | coverage_and_integration |
| `K12/03 Coverage` | core pages not thinner than new peripheral or frontier pages | triggers → `K12/03 Module` depth balance | — |
| `K12/14 Batch` | Required pages at target `authoring_status`; delta applied, both ledgers in sync | emits | coverage_and_integration |
| `K12/14 Batch` | canonical ownership, body links, navigation synchronized | emits | structure_and_links |
| `K12/14 Batch` | Sources synchronized | emits | source_and_currentness |
| `K12/14 Batch` | metadata; registered migrations; AuditPlan `reused_receipt_id`; delta written out; guidance reconciliation; `unresolved_invalidations = 0` | emits | guidance_and_contract |
| `K12/09` Closed List | 1 `check_links`; 2 structural validity; 3 graph JSON and basename candidates | emits | structure_and_links |
| `K12/09` Closed List | 4 Coverage file-count reconciliation | emits | coverage_and_integration |
| `K12/09` Closed List | 5 guidance ID and contract continuity; 7 `check_vocab` | emits | guidance_and_contract |
| `K12/09` Closed List | 6 registered residual-content scan | declared by the registered scan | declared there |

The first two rows are uniform: every item in them emits under the dimension shown, except the graph-impact-rationale item of `K12/04 Source Intake`, which files under coverage_and_integration.

A [[kernel/K12 Quality Assurance/05 Automated and Manual Checks#Domain-specific Checks|K12/05 Domain-specific]] item takes the dimension of the object it checks, filed above or in K12/08, without opening a second receipt for it. Three have no other owner: Task Contract loaded-set resolvability under guidance_and_contract; Standards-migration block owner uniqueness, omission and duplication under coverage_and_integration; MOC, leaf and Read Set target consistency plus the missing Sources, Related and metadata scan under structure_and_links. Short-file and `check_freshness` scans raise candidates only; the changed-scope `check_vocab` self-check is evidence toward Closed List 7.

The `K12/14 Batch` roll-up line covering automated checks, manual content review and the applicable rendering level emits nothing of its own. [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|K12/06]] and [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|K12/15]] state no judgment items: the Completion Gate and the Terminal Audit consume receipts.

Closed List 3 emits a candidate list; whether two candidates are one canonical concept with two owners is decided by the `K12/03 Module` duplicate item.

## Gate Receipt Dimensions

A Gate ID of [[kernel/K00 Standards Control/12 Control Registry#Control Registry|Control Registry]] whose canonical gate is a judgment item filed above or in K12/08 takes that item's dimension. The rest:

| Dimension | Gate IDs |
|---|---|
| guidance_and_contract | `runtime-card-synchronization`; `profile-load`; `runtime-startup-recovery`; `large-scale-execution-admission`; `standards-adoption`; `standards-revalidation`; `guidance-disposition`; `receipt-validity` |
| coverage_and_integration | `required-queue-consistency`; `required-queue-admission`; `required-queue-completion`; `maintenance-completion`; `corpus-plan-semantic-acceptance`; `terminal-proof` |
| structure_and_links | `corpus-plan-structure`; `duplicate-detection` |
| source_and_currentness | `knowledge-freshness` |
| none | `batch-review` and `batch-close`, each binding member receipts that already carry the verdicts; `registered-residual-content`, filed where its `Registered Scan Registry` entry declares |

## Reverse Check

A derived restatement, not the authority: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Reverse Check|K12/08]] owns this check and prevails on disagreement. Every base dimension has an emitting item across the two halves, which are read together for it; no half establishes it alone. K12/08 additionally states what a profile adding numeric obligations should do.
