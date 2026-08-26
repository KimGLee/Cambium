## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|Capability Matrix Contract]].
- Next: [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]].

## Purpose And Ownership

This module owns the cross-instance meaning and lifecycle of the `Gap
Register`. Its closed record shape is owned by the registered `gap-register`
machine contract. K02/03 owns applicability and reconciliation; K02/04 owns
audit and evidence-currentness boundaries. The selected Profile binds the
instance path.

## Gap Register Contract

The `Gap Register` owns the planning history of semantic gaps. A gap is a
missing question, mechanism, relationship, or capability dependency, not a
missing batch, stale receipt, or unchecked task box. The `gap-register`
machine contract is the sole normative source for record fields, closed
values, cardinality, and serialization. This module does not repeat that
contract in prose.

Every gap has a stable identity, a statement, at least one affected capability,
an optional candidate Map owner, lifecycle status, close condition, evidence,
promotion reference, and rationale. Evidence and promoted owners are corpus
artifacts, not adopter runtime state.

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
Additional fields or free-form sections are invalid unless the machine
contract is revised through Standards governance.

## Related

- [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|Corpus Planning Applicability and Lifecycle]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]]
