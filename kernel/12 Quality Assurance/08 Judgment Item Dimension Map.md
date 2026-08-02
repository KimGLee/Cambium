## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].
- Next: [[kernel/12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].

## Purpose

An `AuditReceipt` carries one `dimension` field, holding one of the seven base dimensions fixed in [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Dimension-specific Audit Receipt|12/07]]. This module fixes, for every judgment item the kernel states, which dimension its verdict is filed under and whether it produces a receipt at all. Without the map that field has no determinate value for most kernel checks, and the same work can be filed twice under two names.

## Terms

| Term | Meaning |
|---|---|
| Review dimension | The eleven acceptance words of [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review#Quality Dimensions\|12/01]]: vocabulary and grouping labels, not checks; they do not appear in this map |
| Judgment item | One check that can be run once and returns pass or fail |
| Receipt dimension | The seven values the receipt `dimension` field may take |
| Audit object | What one run of an item proves at one layer, per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Audit Layers\|Audit Layers]] |

A heading is not a judgment item. The test: ask "did this pass?" If the question has to be sent back as "which part?", it is a grouping label.

## Evidence Role

Every judgment item has exactly one evidence role:

- `emits` — produces the canonical receipt for its dimension.
- `consumes` — satisfied by a receipt produced elsewhere; records `reused_receipt_id` under the Reuse Gate and does not change that receipt's dimension.
- `triggers` — raises review candidates only; produces no receipt and cannot fail a gate alone.

An item MUST NOT both emit and consume for the same audit object. Which layer owns a risk object's canonical gate is decided by [[kernel/00 Standards Control/05 Core Principles and Standards Map#Control Registry|Control Registry]]; this module files verdicts under those assignments and does not restate them. The lightweight script receipt of a scoped self-check is evidence toward the canonical receipt, not a second receipt for the same object.

## Uniform Sections

All items in these sections emit under one dimension:

| Section | Items | Dimension |
|---|---|---|
| `12/01 Content` | 8 | content_and_depth |
| `12/12 Substantive Correctness Review` | 3 | content_and_depth |
| `12/02` Level 1 – Level 4 | all | rendering |
| `12/04 Guidance Reconciliation Review` | 11 | guidance_and_contract |
| `12/04 Source Intake And Promotion Review` | 9 | source_and_currentness |

The language-acceptance line of `12/01 Content` is a registry pointer, not a check. The graph-impact-rationale item of `12/04 Source Intake` files under coverage_and_integration.

## Item Map

| Section | Items | Role | Dimension |
|---|---|---|---|
| `12/01 Structure` | opening; section order; no meaningless meta | emits | structure_and_links |
| `12/01 Structure` | note type explicit | consumes ← Closed List 7 | — |
| `12/01 Structure` | no duplicate headings or dates | consumes ← `12/02` Level 0 | — |
| `12/01 Links` | key dependencies; first-occurrence term links; Related not the only place; intake / synthesis / canonical / case relations | emits | structure_and_links |
| `12/01 Links` | parent, prerequisite, dependency links resolve; none unresolved or ambiguous | consumes ← Closed List 1 | — |
| `12/01 Links` | expression-layer structural links | at the gate registered in `Routing And Gate Registry` | declared there |
| `12/01 Accuracy` | formulas, symbols, numeric examples; metric provenance | emits | formula_and_numeric |
| `12/01 Accuracy` | time-sensitive facts; sources support key conclusions | emits | source_and_currentness |
| `12/01 Accuracy` | empirical advice not absolute; claim / inference / synthesis / recommendation distinguished | emits | content_and_depth |
| `12/01 Rendering` | constructs readable as actually used; diagrams not truncated | emits | rendering |
| `12/01 Rendering` | formulas display; alias pipes; image paths and dimensions | consumes ← `12/02` Level 1 | — |
| `12/01 Rendering` | code fences and languages | consumes ← `12/02` Level 0 | — |
| `12/02` Level 0 | heading / fence / link / table pipe; body extraction for structure, duplication, missing sections, term links | emits | structure_and_links |
| `12/02` Level 0 | formula delimiter / image / embed / Mermaid fence | emits | rendering |
| `12/03 Module` | Overview reflects real structure; duplicate canonical notes; orphans; Standards ownership and Read Set reciprocity | emits | structure_and_links |
| `12/03 Module` | unexplained P0 / P1 concepts; prerequisite chain continuous; `Profile Scope` mainline and foundation | emits | coverage_and_integration |
| `12/03 Module` | Case Study usable; depth balance, core not thinner than peripheral | emits | content_and_depth |
| `12/03 Module` | new external sources went through gap analysis | emits | source_and_currentness |
| `12/03 Module` | registered profile synchronization gates | emits | guidance_and_contract |
| `12/03 Coverage` | the other eight items | emits | coverage_and_integration |
| `12/03 Coverage` | core pages not thinner than new peripheral or frontier pages | triggers → `12/03 Module` depth balance | — |
| `12/03 Batch` | Required pages at target `authoring_status`; delta applied, both ledgers in sync | emits | coverage_and_integration |
| `12/03 Batch` | canonical ownership, body links, navigation synchronized | emits | structure_and_links |
| `12/03 Batch` | Sources synchronized | emits | source_and_currentness |
| `12/03 Batch` | metadata; registered migrations; AuditPlan `reused_receipt_id`; delta written out; guidance reconciliation; `unresolved_invalidations = 0` | emits | guidance_and_contract |
| `12/07` Closed List | 1 `check_links`; 2 structural validity; 3 graph JSON and basename candidates | emits | structure_and_links |
| `12/07` Closed List | 4 Coverage file-count reconciliation | emits | coverage_and_integration |
| `12/07` Closed List | 5 guidance ID and contract continuity; 7 `check_vocab` | emits | guidance_and_contract |
| `12/07` Closed List | 6 registered residual-content scan | declared by the registered scan | declared there |

The `12/03 Batch` roll-up line covering automated checks, manual content review and the applicable rendering level emits nothing of its own. [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]] states no judgment items: the Completion Gate and the Terminal Audit consume receipts.

Closed List 3 emits a candidate list; whether two candidates are one canonical concept with two owners is decided by the `12/03 Module` duplicate item. Within one page, duplicate headings are a `12/02` Level 0 finding.

## Reverse Check

Every base dimension has an emitting item. formula_and_numeric draws from two `12/01 Accuracy` items only; the concentration is deliberate but thin, and a profile adding numeric obligations SHOULD register them here rather than widening another dimension.

## Profile Registration

An entry appended through the `Audit Dimension Registry` is a judgment item, not a dimension name. It MUST declare: the receipt dimension it files under (base, or an extension dimension registered in the same file), its audit layer, its audit object, its evidence role, and the single owner of its acceptance predicate. An entry omitting the receipt dimension cannot be filed; one omitting the audit object cannot be told apart from an existing item.

## Related

- [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]]
