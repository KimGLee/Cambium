## Navigation

- Parent: [[kernel/02 Knowledge Base Build Execution Standard|02 Knowledge Base Build Execution Standard]].
- Previous: [[kernel/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]].

## Completion Policy

Completion cannot be declared early for the following reasons:

- Large token or context consumption.
- A large number of files already created.
- Most checkboxes already exist in the profile-registered planning artifact.
- Automated link checks pass.
- The task has been running for a long time.
- `minimum_run_until` or some checkpoint has been reached.
- The Progress Ledger temporarily has no active batch.
- Most pages are already `reviewed`.

A task can only move from `active` to `completion-candidate`, and enters `complete` only after completing the Terminal Audit of the [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]].

The canonical procedure of the Terminal Audit is at [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report#Terminal Audit|Terminal Audit]].

The Terminal Proof proves at least:

```text
scope_reconciled
AND guidance_reconciled
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
- `required_authoring_gaps = 0`: all Required pages have reached the target authoring state, or their disposition has been changed with explicit authorization.
- `unverified_batches = 0`: no batch exists that was only written but not accepted.
- `unresolved_invalidations = 0`: all Required receipts invalidated by content, dependency, contract, Standards, review due, or systemic issues have been re-verified, superseded, or had their disposition changed with authorization.
- `required_QA_passed`: the Single Note, Module, Expression Layer, Source Promotion, and Rendering gates pass per applicable scope; the Expression Layer gate is provided by the profile role bound by the `Routing And Gate Registry`.
- `final_handoff_written`: the remaining optional, deferred, and evidence gaps are made explicit.
- `time_contract_satisfied`: if `minimum_run_until` exists, the current time has reached it; if `hard_stop_at` exists, the user-required stop boundary has not been crossed.

The canonical rule separating authoring completion from evidence closure (including the four executable conditions) is in [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|12/06]]; pages missing body mechanism, Sources, Expression Layer migration, or Required QA remain authoring gaps.

The user MAY pause or cancel the task before the Completion Gate, but that action cannot be reported as completion.

## Final Handoff

The final handoff needs to state:

- Task state, scope version, and standards version.
- Selected Runtime Card IDs and Read Sets, and the final loaded set (artifacts resolved by the `Runtime Card Provider` and modules read back on escalation).
- Contract version, queue revision, and an Amendment Log summary.
- Knowledge architecture and scope.
- Completed modules and their maturity.
- Newly added and migrated content.
- Source Notes, Research Synthesis, and canonical promotions.
- The coverage and readiness of `Expression Layer Entry` outputs, citing the results of the profile expression gate role bound by the `Routing And Gate Registry`.
- QA results.
- Audit Receipt reconciliation: reuse, superseded, invalidated, legacy-evidence, sampling, and systemic expansion.
- Coverage Ledger summary, Required authoring gaps, and Terminal Proof.
- Guidance reconciliation results and records still in `deferred` / `clarification-required`.
- P1 / P2 content not yet covered.
- The optional, deferred, and external evidence backlog, with re-entry conditions.
- The subsequent maintenance approach.

## Related

- [[kernel/00 Standards Overview|Standards Overview]]
- [[kernel/08 Metadata and Status Standard|Metadata and Status Standard]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
