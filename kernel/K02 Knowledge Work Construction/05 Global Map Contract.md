## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]].
- Next: [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]].

## Purpose And Ownership

This module is the sole kernel owner of the exact record contract for the
global map bound as `Global Map`. K02/03 owns its applicability, lifecycle, and
reconciliation. K02/04 owns its runtime, audit, deterministic-check, receipt,
and affected-path boundaries. The selected profile supplies its path; it does
not redefine the record format below.

## Global Map Contract

The `Global Map` is the agent routing map for the corpus as a whole. Profile
Scope remains the sole owner of corpus purpose, intended audience, logical
Layer IDs, their repository-relative directories, and layer responsibilities.
The Corpus Planning slot remains the sole owner of the Matrix and Gap artifact
paths. The Global Map MUST NOT repeat any of those values.

The restricted-YAML document has exactly three top-level fields:
`schema_version: 1`, `entries`, and `typed_dependencies`. Each `entries` item
has exactly `entry_id`, `layer_id`, `canonical_markdown_path`, and
`single_responsibility`. Each `typed_dependencies` item has exactly `edge_id`,
`upstream_entry_id`, `downstream_entry_id`, and `relation_type`.

Entry and edge IDs are stable. Each Profile Scope layer has at least one Map
entry. Each entry identifies an existing canonical Markdown owner inside one
of its layer's registered directories and states that owner's unique
responsibility. Each edge is an explicit,
directed assertion; links, backlinks, co-location, or semantic similarity do
not create an edge. `relation_type` is exactly one of `prerequisite-for`,
`capability-input-to`, `realized-by`, `evidence-input-to`, `system-input-to`,
`control-input-to`, `canonical-source-for`, or `downstream-impact`. Together
the records express the included logical
architecture, Knowledge Spine, owner boundaries, and important prerequisite
or downstream relationships.

The map MUST reflect the current corpus structure and canonical owners. It
contains no free-form sections or additional fields and MUST NOT own capability
maturity, task state, batch state, page disposition, queue order, receipts,
revisions, fingerprints, or completion claims.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
