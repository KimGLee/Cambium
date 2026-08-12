## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]].
- Next: [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]].

## Purpose And Ownership

This module is the sole kernel owner of the applicability, lifecycle, and
reconciliation for the three durable corpus-planning roles defined by
[[kernel/K02 Knowledge Work Construction/05 Global Map Contract|K02/05]],
[[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|K02/06]],
and [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|K02/07]]:
the map bound as `Global Map`, the `Capability Matrix`, and the
`Gap Register`.

The selected profile's `Corpus Planning` slot binds one repository-relative
restricted-YAML path to each role, defines the ranked capability scale and its
target-eligible values, and binds a registered role to the closed
`corpus-plan-semantic-acceptance` decision scope. It supplies domain-specific
bindings only; it does not redefine the roles, record formats, or ownership
boundaries.

All three Profile artifact bindings, every Global Map canonical Entry path,
the Profile Scope layer directories that contain those Entries, and every
promoted Coverage path MUST remain outside `.cambium/`.
Runtime state, Work Specs, receipts, and derived query output MUST NOT become
semantic-planning inputs or canonical corpus owners.

For large-scale corpus construction, corpus migration, or persistent
multi-batch work, `Corpus Planning` MUST use
`applicability.state: configured` before Phase 2 closes. A bounded small task
MAY use `applicability.state: not-applicable` with a nonempty `reason` when it
neither needs nor changes a corpus-wide map, capability model, or semantic-gap
register. `not-applicable` cannot be used after the task relies on any of the
three artifact roles.

## Phase 2: Architecture And Mapping

- Materialize the `Global Map` restricted-YAML artifact.
- Materialize the `Capability Matrix` restricted-YAML artifact.
- Materialize the `Gap Register` restricted-YAML artifact.
- Record the typed dependency graph in the `Global Map`.
- Build the mapping between the selected profile's `Profile Scope` / `Knowledge Spine` and foundation dependencies.
- Mark concepts that are duplicated or have unclear ownership.
- Mark conclusions that need source intake, cross-source synthesis, or re-verification.
- Draw up the directory migration table, and build the expression-artifact mapping via the selected profile's `Expression Layer Entry` and `Routing And Gate Registry` roles.

Before the mapping is complete, do not bulk-delete original content.

Artifact names and directories are profile bindings. They do not change the
three roles or the closed contracts defined by K02/05, K02/06, and K02/07.

## Lifecycle And Reconciliation

The three artifacts follow one planning lifecycle:

1. Bind their paths, capability scale, and pass authority through the selected profile.
2. Establish or reconcile the `Global Map` before bulk deletion, migration, or corpus-wide expansion. One corpus cannot obey that order — the one that does not exist yet. The Map names existing canonical owners, so a corpus whose Profile Scope layer directories hold none has nothing to establish, and [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate|K00/13]] admits large-scale work only against a configured plan. That ordering has no resolution in this revision: it is recorded here as a known admission-ordering gap rather than left for each adopter to discover, and closing it needs a writer that can record a task's initial planning selections, which does not exist yet.
3. Establish the `Capability Matrix` from testable corpus capabilities and current canonical owners rather than from file counts alone.
4. Record newly discovered, not-yet-admitted semantic gaps in the `Gap Register`.
5. Promote an accepted gap through the canonical Coverage and Queue planning path; do not schedule it by editing the register.
6. After accepted corpus changes, update the affected map entries, capability records, and gap handoffs without rewriting runtime history.
7. Before module or corpus-planning acceptance, reconcile the artifacts against the actual corpus, the selected `Profile Scope`, and one another, then obtain the registered pass authority's decision.

Stable Entry, Capability, and Gap identifiers MUST be retained when their
semantic identity is unchanged. A path rename or replacement is one controlled
migration: update the Profile binding and every explicit Map, Matrix, Gap,
Coverage, Queue, or Work Spec reference against the same accepted snapshot.
The closed planning schemas do not acquire an undeclared successor field.
Rejected or superseded Gap conclusions retain their status and rationale in
the existing Gap record.
