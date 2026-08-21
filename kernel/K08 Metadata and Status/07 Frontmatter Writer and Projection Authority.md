## Navigation

- Parent: [[kernel/K08 Metadata and Status Standard|K08 Metadata and Status Standard]].
- Previous: [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|Frontmatter Applicability Contract]].
- Next: [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract|Relationship Metadata Contract]].

## Frontmatter Writer and Projection Authority

Fields sharing one YAML block does not mean they share one writer. This leaf owns, per field class: the canonical owner, the allowed writer, the write-back timing, and the invalidation rule. It does not redefine field values, the Queue state machine, or evidence policy.

- **User state** (`learning_status`): user-owned. Only the user or an explicitly authorized learning flow writes it; bulk knowledge-base building never fills it, including to silence a checker candidate. Absence carries no quality meaning and never enters authoring or coverage completion.
- **Derived freshness** (`review_by`): computed by `Tools/check_freshness.py` from the valid completed-event baseline and resolved volatility policy owned by [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|K08/05]]. By default it appears only in tool output, reports, and receipts, and is **not persisted** to the page — a persisted derived date goes stale the moment its inputs change. A real external validity date (a legal, contract, version, or expiry) is not derived freshness: it uses the explicitly named `source_valid_until` field or a formal override, never `review_by`.
- **State and event projections**: the Coverage Ledger and Required Queue own
  the current values and evidence pointers; the page only mirrors them.
  `coverage_disposition`, `authoring_status`, and `next_batch` report lifecycle
  state. `last_content_modified` is advanced only by a guarded Integrator
  content-change event bound to the new semantic content fingerprint.
  `last_reviewed` is advanced only by consumed review evidence bound to that
  same fingerprint. These completed core events replay under their producer
  era: a later Profile or tool implementation revision does not erase the
  fact, while target, value, receipt graph, and current semantic fingerprint
  still bind exactly. Profile-owned readiness state is different and remains
  subject to the currently selected typed Profile. A content change
  invalidates the prior review authority instead of fabricating a review
  date. `last_verified` remains a separate
  external-verification event and is never advanced by a close without its
  own evidence. The compiled metadata execution contract names each owner,
  source adapter, writer capability, timing, and invalidation rule; the generic
  projector reconciles the page copy to that owner and never treats a hand edit
  as execution reality.
- **Profile expression bindings** (readiness axes and expression relations such as a profile's card binding): the kernel owns only this authority rule; the selected profile registers the concrete fields. A `mapped`-class value requires a resolvable reciprocal binding; a `ready`-class value is granted only by the profile's registered expression gate or receipt, never inferred from file existence or link resolvability. A profile with no expression layer marks these fields `forbidden`.

## Writer Rules

Applicability and mutation authority are independent axes. A writer may change
only a transition granted to its installed capability by the compiled metadata
execution contract, after resolving the declared owner/source/evidence and
write timing. Compilation fails both when a machine-managed transition has no
writer and when an installed writer claims an undeclared transition. A checker
never rewrites user-owned state or performs an authority judgment. Writers
re-parse targets and use the shared guarded transaction boundary; owner state,
evidence pointer, and page projection either reconcile together or fail closed.
Writer overreach, stale evidence, and a page projection disagreeing with its
owner are checkable defects. Page frontmatter never becomes a second Queue or
a personal learning database.
