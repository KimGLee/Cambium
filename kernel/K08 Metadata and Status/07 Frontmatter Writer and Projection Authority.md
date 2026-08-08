## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|Frontmatter Applicability Contract]].
- Next: [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract|Relationship Metadata Contract]].

## Frontmatter Writer and Projection Authority

Fields sharing one YAML block does not mean they share one writer. This leaf owns, per field class: the canonical owner, the allowed writer, the write-back timing, and the invalidation rule. It does not redefine field values, the Queue state machine, or evidence policy.

- **User state** (`learning_status`): user-owned. Only the user or an explicitly authorized learning flow writes it; bulk knowledge-base building never fills it, including to silence a checker candidate. Absence carries no quality meaning and never enters authoring or coverage completion.
- **Derived freshness** (`review_by`): computed by `Tools/check_freshness.py` from `last_verified` plus the volatility or profile interval. By default it appears only in tool output, reports, and receipts, and is **not persisted** to the page — a persisted derived date goes stale the moment its inputs change. A real external validity date (a legal, contract, or version expiry) is not derived freshness: it uses the explicitly named `source_valid_until` field or a formal override, never `review_by`.
- **State projections** (`coverage_disposition`, `next_batch`): the Coverage Ledger and Required Queue are the sole owners. `coverage_disposition` MAY persist as a tool-controlled page projection that a checker reconciles against the owner; hand-editing it never changes execution reality. `next_batch` lives by default only in the Queue and derived reports; if kept as a page field it is written only by a projector and invalidated automatically, never hand-filled.
- **Profile expression bindings** (readiness axes and expression relations such as a profile's card binding): the kernel owns only this authority rule; the selected profile registers the concrete fields. A `mapped`-class value requires a resolvable reciprocal binding; a `ready`-class value is granted only by the profile's registered expression gate or receipt, never inferred from file existence or link resolvability. A profile with no expression layer marks these fields `forbidden`.

## Writer Rules

Tools write only fields the compiled contract declares `derived` or `projection`; a checker never infers or rewrites a `user-owned` value or any value requiring an authority decision. A writer re-parses the target before writing and uses an atomic write. Writer overreach, a projection disagreeing with its canonical owner, and a hand-filled derived value are all checkable defects — `Tools/check_page_contract.py` reports them under the same advisory contract as [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]]. Page frontmatter never becomes a second Queue or a personal learning database.
