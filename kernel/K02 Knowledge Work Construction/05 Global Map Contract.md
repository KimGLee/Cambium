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

The `global-map` machine contract is the unique normative carrier of the
document's closed fields and relationship vocabulary. Each entry has a stable
identity, belongs to one Profile Scope layer, resolves to one canonical
Markdown owner, and states that owner's unique responsibility. Each typed edge
has a stable identity and is an explicit directed assertion between registered
entries; links, backlinks, co-location, or semantic similarity do not create an
edge.

Evidence and expression edges preserve ownership direction: sources may feed
synthesis and canonical conclusions, and an expression artifact may present a
canonical owner, but no downstream artifact becomes that owner's replacement.
Only real dependencies gain edges.

The map MUST reflect the current corpus structure and canonical owners. It
contains no free-form sections or additional fields and MUST NOT own capability
maturity, task state, batch state, page disposition, queue order, receipts,
revisions, fingerprints, or completion claims.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
