## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/02 Rendering Verification|Rendering Verification]].
- Next: [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].

## Module Review

Before a module is complete, check:

- Whether the Overview reflects the real module structure.
- Whether the coverage matrix still has unexplained P0 / P1 concepts.
- Whether the prerequisite chain is continuous.
- Whether the mainline dependencies and foundation preservation requirements declared by the selected profile's `Profile Scope` remain intact.
- Whether duplicate canonical notes exist.
- Whether orphan notes exist.
- Whether every in-scope expression artifact passes R05 synchronization and any supplemental profile gate.
- Whether the Case Study can use the module's knowledge.
- Whether new external sources went through gap analysis rather than producing isolated pages by article title.
- Whether file depth is balanced; core topics MUST NOT be visibly thinner than peripheral topics.
- Standards modules MUST additionally confirm that the Standard Module MOC matches the actual leaf files, that each original section has exactly one owner, and that Applicable Read Sets are navigable in both directions.

Module Review first consumes the valid AuditReceipts of batches already closed under [[kernel/K12 Quality Assurance/14 Batch Review#Batch Review|Batch Review]], then reviews the owner, dependency, coverage, and navigation invariants that can only be judged across batches. Local mechanisms with no relevant change SHOULD NOT be re-reviewed page by page; when receipts are missing or invalidated, or sampling exposes a systemic problem, expand the scope per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Coverage Reconciliation Review

Before a module or long task completes, the Coverage Ledger MUST be reconciled against the actual file system, the scope contract, and the competency matrix:

- Every in-scope file has exactly one inventory record.
- Every Required knowledge object not yet created still has an explicit record.
- Excluded directories are not counted as deliverables or accidentally modified.
- No P0 / P1 core, process-flow, system, or risk/control page is `unassessed`.
- Every Required item that has not reached its target state appears in exactly one non-terminal current Queue manifest and has a consistent Coverage `next_batch` projection; the same object may remain in an immutable closed predecessor manifest identified by Coverage `batch`.
- `deferred` has a reason, a re-entry condition, and an owner; `excluded` has a scope basis.
- Sequence or progress checkboxes, file existence, resolvable wiki links, and `Related` references are not treated as authoring completion; for status separation see [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence And Progress Semantics]].
- Core pages are not visibly thinner than newly created peripheral or frontier pages.
- Coverage Ledger summary counts match the automated scan counts.
- For each Queue item, its explicit manifest equals the set projected to that batch by Coverage and its `record_count` equals the manifest size; no Coverage object names an unknown batch, no Queue manifest names an unknown object, and no `closed` item remains a Coverage `next_batch`.

Within the local receipt trust boundary, the current `Tools/check_queue.py` receipt records that these cross-ledger conditions matched the checked bytes and state. Module Review consumes that receipt and reviews the semantic coverage around it; it does not implement a second Queue validator.

Line counts and section counts can only trigger review candidates. An Atomic Term Note MAY deliberately stay concise; Core, Process, System, and Risk/Control pages MUST have their question coverage checked by note type.
