## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]].
- Next: [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]].

## Purpose And Ownership

This module is the sole kernel owner of the exact record contract for the
`Gap Register`. K02/03 owns its applicability, lifecycle, and reconciliation.
K02/04 owns its runtime, audit, deterministic-check, receipt, and affected-path
boundaries. The selected profile supplies its path; it does not redefine the
record format below.

## Gap Register Contract

The `Gap Register` owns the planning history of semantic gaps. A gap is a
missing question, mechanism, relationship, or capability dependency, not a
missing batch, stale receipt, or unchecked task box. Its restricted-YAML
document has exactly `schema_version: 1` and `gaps`. Each gap record has
exactly `gap_id`, `gap_statement`, `capability_ids`,
`candidate_owner_entry_id`, `status`, `close_condition`, `evidence_paths`,
`promoted_coverage_path`, and `rationale`.

`capability_ids` and `evidence_paths` are explicit YAML lists, including when
empty. `candidate_owner_entry_id` is either `null` or an existing Global Map
Entry ID. `promoted_coverage_path` is `null` before promotion and equals the
canonical Coverage object path after promotion. Evidence and promoted paths
remain outside `.cambium/`.

The status vocabulary and ownership boundary are:

```text
candidate -> confirmed -> promoted -> resolved
     |           |
     +-----------+-> deferred
     +-----------+-> rejected
```

- `candidate`: discovered but not yet accepted as a real corpus gap; path and owner may be unknown.
- `confirmed`: accepted as a real semantic gap, but its final target or disposition may still be unresolved.
- `promoted`: admitted into canonical Coverage; `Promoted Coverage path` names that object, whose Coverage row owns target path, owner, and disposition. Promotion does not itself mean `required` or scheduled.
- `resolved`: the close condition is satisfied at the promoted Coverage path and the row identifies current evidence.
- `deferred`: an unpromoted candidate or confirmed gap is not admitted now; the rationale states why and what would re-open the decision.
- `rejected`: an unpromoted candidate or confirmed item is judged not to be a corpus gap; the rationale preserves the decision.

When a gap becomes `promoted`, Coverage owns its disposition and object state.
Only a Required, unfinished promoted object enters the Required Queue; optional,
deferred, or excluded Coverage does not acquire a fictitious Queue item. The
register retains the stable ID, target, rationale, and status as planning
history. A promoted row remains `promoted` until semantic resolution even when
Coverage later defers or excludes its object; the register MUST NOT copy the Coverage disposition, batch assignment,
Queue lifecycle, or receipts. Rejection, deferral, promotion, and resolution
retain their reason; candidates MUST NOT disappear silently.
No free-form sections or additional fields are permitted.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
