## Navigation

- Parent: [[kernel/K02 Knowledge Work Construction Standard|K02 Knowledge Work Construction Standard]].
- Previous: [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]].
- Next: [[kernel/K02 Knowledge Work Construction/03 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]].

## Coverage Reconciliation

Coverage reconciliation is executed at least at the following points:

1. After the Phase 1 inventory completes.
2. After each batch's serial merge closes (at this point only file-count reconciliation is executed, i.e. item 4 of the Closed List).
3. After a scope or Standards version change.
4. After accepted guidance changes coverage or priority.
5. Before the task enters `completion-candidate`.

At every reconciliation, the set of objects projected to each batch in Coverage MUST equal that Queue item's explicit manifest, and its count MUST equal `record_count`. Required objects may not be orphaned from the Queue, assigned to an unknown batch, or silently disappear through a cancelled item. `Tools/check_queue.py` is the sole deterministic owner of this cross-ledger set comparison.

Reconciliation recomputes only the receipt validity affected by file, scope, guidance, or Standards changes; one unrelated modification cannot invalidate all content review dates, nor can `last_reviewed` be treated as proof of continued validity. File count, link, and control-plane invariants concerning the final graph state are still computed in full per gate.

The reconciliation question checklist is governed by the Coverage Reconciliation Review in [[kernel/K12 Quality Assurance/03 Module and Coverage Review|K12/03]].

Line counts, file existence, and link resolution are used only to surface candidate anomalies; they cannot replace note-type-aware content review.
