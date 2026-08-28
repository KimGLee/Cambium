## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Next: [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]].

## Coverage Inventory Boundary

Inventory materializes the knowledge objects governed by the current Profile Scope into the `coverage-ledger` machine contract. The selected Profile owns the concrete scope, exclusions, directory bindings, and domain values; Kernel does not enumerate instance paths or current records.

The inventory accounts for every in-scope page and every Required object that does not yet exist, together with the stable identity, ownership, disposition, evidence, and planning relationships required by the machine contract. This module owns the resulting Coverage invariants, not an execution sequence.

The inventory MUST form a persistent, queryable Coverage Ledger; it cannot exist only in transient analysis or in the executor's memory. The Coverage Ledger MAY be split by domain, but it MUST have one summary entry point and satisfy:

- Every in-scope Markdown file has exactly one record.
- Knowledge objects not yet created but belonging to Required coverage also have records.
- File system counts, the excluded scope, and Ledger summary counts can be reconciled.
- Legacy pages without metadata default to `authoring_status: unassessed` and cannot be treated as drafted merely because the file exists.
- `authoring_status: reviewed` is evidence-bound. The record names current
  evidence that earned the status; an unsupported value is a re-review
  candidate rather than a pass. Existing unsupported records require an
  explicit migration disposition or a bounded policy exception with a stated
  end; prose alone cannot authorize them. The stable exception identity,
  record-count limit domain, and effective-policy currentness payload are
  registered once in
  [`contract-exception-policy-base.yaml`](../K00%20Standards%20Control/contract-exception-policy-base.yaml);
  this page remains the semantic owner of why `reviewed` must name its
  evidence era.
- Every unfinished Required item has an explicit `next_batch`.
- Every `deferred` and `excluded` item has a reason and a re-entry condition or scope basis.

The Coverage Ledger is the authoritative record of page/object-level coverage. Its object-side `batch` / `next_batch` projection MUST equal the frozen manifests in the canonical [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue]]; the Queue owns batch lifecycle, while the Progress Ledger owns only whole-task state and accepted Queue references.

The Ledger also carries the Queue proposal inputs defined by the `coverage-ledger` machine contract. These inputs do not own accepted Queue order or lifecycle and remain separate from page records, so a successor can have a different configuration without rewriting closed history.

## Machine-readable Ledger

The `coverage-ledger` machine contract is the unique normative carrier of the Ledger's closed fields and syntax. The adopter runtime owns its current values. A Markdown view is optional, derived, and never a basis for reconciliation or completion.
