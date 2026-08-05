## Navigation

- Parent: [[kernel/K02 Knowledge Base Build Execution Standard|K02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].
- Next: [[kernel/K02 Build Execution/08 Progress Ledger|Progress Ledger]].

## Completion Policy

Completion cannot be declared early for the following reasons:

- Large token or context consumption.
- A large number of files already created.
- Most checkboxes already exist in the profile-registered planning artifact.
- Automated link checks pass.
- The task has been running for a long time.
- `minimum_run_until` or some checkpoint has been reached.
- The Queue-derived view temporarily has no `open` batch.
- Most pages are already `reviewed`.

For `completion_semantics: build`, a task moves from `active` to
`completion-candidate`, then enters `complete` only after completing the
Terminal Audit of the [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]].

The canonical procedure of the Terminal Audit is at [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]].

The Terminal Proof proves at least:

```text
scope_reconciled
AND guidance_reconciled
AND remaining_required_work_units = 0
AND required_authoring_gaps = 0
AND unverified_batches = 0
AND unresolved_invalidations = 0
AND required_QA_passed
AND final_handoff_written
AND time_contract_satisfied
```

Where:

- `scope_reconciled`: the Coverage Ledger is reconciled against the file system, scope, and exclusions.
- `guidance_reconciled`: all accepted guidance has been mapped, verified, explicitly deferred, or superseded by later guidance; no unclassified, accepted-but-unmapped, or implemented-but-unverified items exist.
- `remaining_required_work_units = 0`: `Tools/check_queue.py . --require-complete` passes against the frozen Queue, every Required work unit is `closed`, and any retained `cancelled` history has a matching scope or disposition Amendment so that it no longer represents Required work.
- `required_authoring_gaps = 0`: all Required pages have reached the target authoring state, or their disposition has been changed with explicit authorization.
- `unverified_batches = 0`: no batch exists that was only written but not accepted.
- `unresolved_invalidations = 0`: all Required receipts invalidated by content, dependency, contract, Standards, review due, or systemic issues have been re-verified, superseded, or had their disposition changed with authorization.
- `required_QA_passed`: the Single Note, Module, R05 Expression Layer, Source Promotion, Rendering, and applicable supplemental profile gates pass for their scope; the profile binds the concrete expression artifact but does not own the R05 kernel floor.
- `final_handoff_written`: the remaining optional, deferred, and evidence gaps are made explicit.
- `time_contract_satisfied`: if `minimum_run_until` exists, the current time has reached it; if `hard_stop_at` exists, the user-required stop boundary has not been crossed.

The canonical rule separating authoring completion from evidence closure (including the four executable conditions) is in [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|K12/06]]; pages missing body mechanism, Sources, Expression Layer migration, or Required QA remain authoring gaps.

The user MAY pause or cancel the task before the Completion Gate, but that action cannot be reported as completion.

## Maintenance Completion Policy

For `completion_semantics: maintenance`, the Task Contract instead selects the
bounded predicate in [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|K00/06]]. The task MUST NOT enter
`completion-candidate`, combine R08, or produce Terminal Proof. When persistent
state applies, K02/09 owns the maintenance gate and `update_task.py` consumes
its pass. A direct `planned -> complete` edge is limited to a nonempty Queue
whose batches were all validly cancelled before any opened; otherwise closure
starts from `active`. After interruption, reuse a passed gate only when resume
finds it compatible with current state and evidence; a stale gate is rerun.

## Final Handoff

The final handoff states:

- Task state, scope version, and standards version.
- Selected Rxx route IDs and Runtime Card paths, and the final loaded set (any combined namespaced profile route plus every Read Set or leaf path actually read back).
- Contract version, `completion_semantics`, Queue path, `queue_revision`, `queue_state_revision`, Queue SHA-256 fingerprint, the applicable completion receipt, and an Amendment Log summary.
- Knowledge architecture and scope.
- Completed modules and their maturity.
- Newly added and migrated content.
- Source Notes, Research Synthesis, and canonical promotions.
- The coverage and readiness of `Expression Layer Entry` outputs, citing the R05 results and any supplemental profile gate results.
- QA results.
- Audit Receipt reconciliation: reuse, superseded, invalidated, legacy-evidence, sampling, and systemic expansion.
- Coverage Ledger summary, Required Queue closed/cancelled history and remaining count, Required authoring gaps, and either the build Terminal Proof or the maintenance completion receipt.
- Guidance reconciliation results and records still in `deferred` / `clarification-required`.
- P1 / P2 content not yet covered.
- The optional, deferred, and external evidence backlog, with re-entry conditions.
- The subsequent maintenance approach.

## Related

- [[kernel/K00 Standards Overview|Standards Overview]]
- [[kernel/K08 Metadata and Status Standard|Metadata and Status Standard]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
