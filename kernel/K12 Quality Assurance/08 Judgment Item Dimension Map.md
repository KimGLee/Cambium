## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].
- Next: [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].

## Purpose

An `AuditReceipt` carries one `dimension` from [`audit-dimension-base.yaml`](audit-dimension-base.yaml). This module maps page-level judgments; K12/18 maps higher layers, and [`batch-review-obligation-registry.yaml`](batch-review-obligation-registry.yaml) maps M-tier atoms.

## Terms

| Term | Meaning |
|---|---|
| Review dimension | The eleven acceptance labels of [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#Quality Dimensions\|K12/01]]; they are not checks and do not appear here |
| Judgment item | One check that can be run once and returns pass or fail |
| Receipt dimension | A base value registered in `audit-dimension-base.yaml`, or a valid extension registered by the selected Profile |
| Audit object | What one run of an item proves at one layer, per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Audit Layers\|Audit Layers]] |

A heading is not a judgment item. The test: ask "did this pass?" If the question has to be sent back as "which part?", it is a grouping label.

## Evidence Role

Every judgment item has exactly one evidence role. The closed role namespace is owned by `audit-dimension-base.yaml`; the meanings are:

- `emits` — produces the canonical receipt for its dimension.
- `consumes` — satisfied by a receipt produced elsewhere; records `reused_receipt_id` under the Reuse Gate and does not change that receipt's dimension.
- `triggers` — raises review candidates only; produces no receipt and cannot fail a gate alone.

An item MUST NOT both emit and consume for the same audit object. [[kernel/K00 Standards Control/12 Control Registry#Control Registry|K00/12]] owns its canonical gate; this module only files the verdict. A scoped self-check is evidence toward that verdict, not a second receipt.

## Uniform Sections

All items in these sections emit under one dimension:

| Section | Items | Dimension |
|---|---|---|
| `K12/01 Content` | 8 | content_and_depth |
| `K12/12 Substantive Correctness Review` | 3 | content_and_depth |
| `K12/02` Level 1 – Level 4 | all | rendering |

The language-acceptance line of `K12/01 Content` is a registry pointer, not a check.

## Item Map

| Section | Items | Role | Dimension |
|---|---|---|---|
| `K12/01 Structure` | opening; section order; no meaningless meta | emits | structure_and_links |
| `K12/01 Structure` | note type explicit | consumes ← Closed List 7 | — |
| `K12/01 Structure` | no duplicate headings or dates | emits | structure_and_links |
| `K12/01 Links` | key dependencies; first-occurrence term links; Related not the only place; intake / synthesis / canonical / case relations | emits | structure_and_links |
| `K12/01 Links` | parent, prerequisite, dependency links resolve; none unresolved or ambiguous | consumes ← Closed List 1 | — |
| `K12/01 Links` | expression-layer structural links | consumes ← R05 bidirectional binding | — |
| `K12/01 Accuracy` | formulas, symbols, numeric examples; metric provenance | emits | formula_and_numeric |
| `K12/01 Accuracy` | time-sensitive facts; sources support key conclusions | emits | source_and_currentness |
| `K12/01 Accuracy` | empirical advice not absolute; claim / inference / synthesis / recommendation distinguished | emits | content_and_depth |
| `K12/01 Rendering` | constructs readable as actually used; diagrams not truncated | emits | rendering |
| `K12/01 Rendering` | alias pipes; fence closure | consumes ← applicable `K12/02` predicate | — |
| `K12/01 Rendering` | formulas, image paths, dimensions | consumes ← selected Profile Rendering Contract when registered | — |
| `K12/01 Rendering` | code-fence language appropriateness | emits | rendering |
| `K12/02` Level 0 | Markdown fence closure; canonical wiki-link resolution | emits | structure_and_links |
| `K12/02` Level 0 | Mermaid fence closure | emits | rendering |
| `K12/02` Level 1 | Markdown-table delimiter, column count, and escaped wiki alias pipe | emits | rendering |

Duplicate-heading identity stays a K12/01 judgment until it has one normalization contract. The K12/02 rows map only predicates admitted by [`deterministic-rendering-contract.yaml`](deterministic-rendering-contract.yaml); its gaps emit nothing and cannot pass. M-tier roles, selectors, and explicit holds are read only from the M registry.

A [[kernel/K12 Quality Assurance/05 Automated and Manual Checks#Manual Checks|K12/05 Manual]] item reviewing one page emits under content_and_depth, except its three visual-escalation items, which emit under rendering.

## Reverse Check

Every base dimension has an emitting item across this map, the M registry, and K12/18. `formula_and_numeric` remains deliberately thin; a Profile adding numeric obligations SHOULD register them rather than widen another dimension.

## Profile Registration

An entry appended through the `Audit Dimension Registry` is a judgment item, not a dimension name. It MUST declare: the receipt dimension it files under (base, or an extension dimension registered in the same file), its audit layer, its audit object, its evidence role, and the single owner of its acceptance predicate. An entry omitting the receipt dimension cannot be filed; one omitting the audit object cannot be told apart from an existing item. `Predicate owner` is a `profile-load` dependency in this Profile; a fragment MUST name exactly one heading.

## Related

- [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K00 Standards Control/12 Control Registry|Control Registry]]
- [`audit-dimension-base.yaml`](audit-dimension-base.yaml)
