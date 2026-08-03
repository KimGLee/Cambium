## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].

## Control Registry

The [[kernel/00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]] governs content rules — "where the rule lives"; this Control Registry governs control obligations — "where the check happens". Each risk object has one and only one canonical gate; other layers only verify that a receipt exists and has not been invalidated, and do not re-check.

| Risk object | Canonical gate (sole) | Behavior of other layers |
|---|---|---|
| Runtime Card completeness and source synchronization | Governance close: [[kernel/00 Standards Control/03 Standards Governance#Revision Write-back Checklist|Revision Write-back Checklist]] runs `Tools/stamp_cards.py . --check` | Routine tasks consume the kernel Cards; profile loading cannot waive the gate, and knowledge-page scans exclude compiled Cards rather than re-validating them |
| Wiki link integrity | Batch close: [[kernel/12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Closed List]] check_links produces the receipt | Note close: only this page's `--scope` self-check; migration/retirement: targeted retargeting only; the Terminal Audit verifies the last batch's receipt and does not re-run |
| Frontmatter vocabulary | Batch close: [[kernel/12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Closed List]] item 7 check_vocab produces the receipt | Note close: `--scope` self-check; the Terminal Audit trusts the receipt |
| Concurrent write conflicts | At batch activation: the integrator runs the manifest intersection check per Coverage `next_batch` ([[kernel/02 Build Execution/05 Batch Execution|02/05]] Concurrent Batches) | Concurrent batches write only their own manifest pages, receipts directory, and delta files; global state files are integrator-exclusive |
| Content correctness (manual) | Note close: [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] review by tier | Batch-level manual review scope = changed ∪ invalidated ∪ sampled; long-term P0 assurance is carried by freshness re-review; the Terminal Audit verifies receipts + bounded sampling |
| Coverage reconciliation | Batch close: file-count only (Closed List item 4); the issue list runs per [[kernel/12 Quality Assurance/03 Module and Coverage Review|12/03]] before module completion and completion-candidate | Once after inventory and once on scope/guidance changes; no reconciliation at batch start; before completion-candidate it merges with Terminal Audit step 4 |
| Standards version consistency | Automatic version self-check at batch activation: [[kernel/12 Quality Assurance/10 Standards Version Adoption#Active-task Adoption|Active-task Adoption]] | With a delta, incremental adoption; with no delta, a one-line receipt; the Terminal Audit validates via check_proof |
| Guidance disposition | One full disposition at intake: [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment|02/02]] (threshold: significant Guidance) | Batch close reconciles only the increment after `last_reconciled_guidance_id`; the Terminal Audit verifies dispositions read-only from the ledger |
| Receipt validity | AuditPlan once before batch close: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] | At batch start only the Receipt Register is loaded; the Reuse Gate conditions remain |
| Rendering | Note close Level 0/1: [[kernel/12 Quality Assurance/02 Rendering Verification|12/02]] | Batch close: one enumerated check item; the Terminal Audit trusts the receipt |
| Registered residual-content scan | Batch close: [[kernel/12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Closed List]] item 6 + the `Registered Scan Registry` residual-scan hook | Other layers reference the Closed List and the registered hooks; no separate corpus-wide scan |
| Duplicate detection | Maintenance runs and governance tasks: [[kernel/12 Quality Assurance/05 Automated and Manual Checks|12/05]] duplicate_check | At batch level only the Closed List's basename-level check; paragraph-level scans do not run every batch |
| Knowledge freshness | check_freshness at maintenance-run start: [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|08/05]] | Not in the batch automatic check list |
| Depth balance | Module close: [[kernel/12 Quality Assurance/03 Module and Coverage Review#Module Review|12/03]] Module Review | Coverage Reconciliation's core-versus-frontier line raises review candidates only and emits no receipt |
| Prerequisite completeness | Module close: [[kernel/12 Quality Assurance/03 Module and Coverage Review#Module Review|12/03]] Module Review | check_links owns link resolution; unexplained P0 / P1 concepts and chain continuity are judged from content and are not re-derived from link results |
| Canonical ownership uniqueness | Module close: [[kernel/12 Quality Assurance/03 Module and Coverage Review#Module Review|12/03]] Module Review duplicate item | Closed List item 3 produces basename candidates only; duplicate headings inside one page are a [[kernel/12 Quality Assurance/02 Rendering Verification|12/02]] Level 0 finding |
