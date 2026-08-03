## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/07 Completion and Handoff|Completion and Handoff]].

## Progress Ledger

An ultra-long task requires separate records of:

- Task state.
- Objective, contract version, scope version, queue revision, active batch revision, exclusions, and standards version.
- Selected Rxx route IDs and Runtime Card paths, the loaded set (any combined namespaced profile route and every Read Set or leaf path actually read back), version resolution results, and pending gate items.
- `minimum_run_until`, `checkpoint_at`, `hard_stop_at`.
- Current phase.
- Active batches (≤ `concurrency_cap`), the merge queue, and the ordered Required Queue.
- Completed files.
- Coverage counts by authoring status and disposition.
- Batch review status.
- Audit snapshot, AuditPlan, receipt register reference, reused / superseded / invalidated receipts, unresolved invalidations, and systemic expansion.
- Evidence maturity and source review status.
- Link and rendering checks.
- Open questions.
- Known gaps.
- Deferred signals, contested claims, and superseded conclusions.
- Next dependency.
- Amendment Log, pending guidance, and last reconciled guidance ID.
- Last accepted checkpoint.
- Terminal Audit status and Terminal Proof.

Progress is measured by quality state, not by the cumulative count of created files.

The Progress Ledger cannot use profile-registered hub checkboxes or the user's `learning_status` to compute build progress. Page writing completion, Expression Layer coverage and readiness, evidence maturity, and personal learning progress MUST be summarized separately.

## Machine-readable Ledger

The canonical form of the Progress Ledger is YAML; the schema is at `Tools/schemas/progress_ledger.template.yaml`, and only the restricted subset syntax declared in the template header comment is allowed. A markdown prose view is optional, derived from the YAML, and not a basis for reconciliation. When resuming a task, load the YAML Ledger directly (together with the Coverage Ledger) instead of re-reading a prose checkpoint.
