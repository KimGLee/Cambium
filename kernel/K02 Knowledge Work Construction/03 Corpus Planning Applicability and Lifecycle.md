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

[`corpus-planning-contract.yaml`](corpus-planning-contract.yaml)
is the unique machine carrier of this slot envelope, its two applicability
branches, the artifact-role mapping, and the closed decision-scope identity.
The selected Profile supplies only one instance of that shape; a checker or
consumer MUST project the closed shape from this registry rather than retain a
second field set or branch algorithm.

All three Profile artifact bindings, every Global Map canonical Entry path,
the Profile Scope layer directories that contain those Entries, and every
promoted Coverage path MUST remain outside adopter runtime state.
Runtime state, Work Specs, receipts, and derived query output MUST NOT become
semantic-planning inputs or canonical corpus owners.

For large-scale corpus construction, corpus migration, or persistent
multi-batch work, `Corpus Planning` MUST use
`applicability.state: configured` before Phase 2 closes. A bounded small task
MAY use `applicability.state: not-applicable` with a nonempty `reason` when it
neither needs nor changes a corpus-wide map, capability model, or semantic-gap
register. `not-applicable` cannot be used after the task relies on any of the
three artifact roles.

## Planning Result

A configured plan materializes the Global Map, Capability Matrix, and Gap
Register under their machine contracts. Together they express the typed
dependency graph, the relationship between Profile Scope and foundational
owners, capability coverage, unresolved semantic gaps, and the accepted handoff
to Coverage. Until those relationships are reconciled, bulk deletion or
corpus-wide migration is not admissible.

Artifact names and directories are profile bindings. They do not change the
three roles or the closed contracts defined by K02/05, K02/06, and K02/07.

## Lifecycle And Reconciliation

The three artifacts follow one planning lifecycle:

1. Bind their paths, capability scale, and pass authority through the selected profile.
2. Establish or reconcile the `Global Map` before bulk deletion, migration, or
   corpus-wide expansion. A new empty corpus first creates a bounded,
   user-confirmed set of canonical owners; only existing owners may enter the
   Map. Moving from `not-applicable` to `configured` is an ordinary authorized
   Profile adoption. Candidate artifacts acquire no authority before that
   adoption commits.
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
