## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].
- Next: [[kernel/K00 Standards Control/11 Standards Map and Rule Registry|Standards Map and Rule Registry]].

## Purpose

This module owns the ordered sequence one batch runs, from the version self-check that opens it to the condition that lets it close. It is read at each batch activation, including on resume. It fixes the order of the steps; batch size, concurrency admission, and who may write the global ledgers are decided by [[kernel/K02 Build Execution/05 Batch Execution|K02/05]].

## Batch Execution Checklist

1. Version self-check: compare the current version in [[kernel/K00 Standards Control/03 Standards Governance|K00/03]] with the contract-frozen version; with a delta, adopt incrementally per [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]] Active-task Adoption; with no delta, record a one-line receipt. Standards changes are discovered by the batch-activation self-check; user notification serves only as a reminder.
2. Reconcile incremental guidance: reconcile only the Guidance Events after `last_reconciled_guidance_id` against the Amendment Log.
3. Select the next batch from the ordered Required Queue.
4. Resolve note type, canonical owner, and target status.
5. Resolve prerequisite and foundation gaps.
6. Collect and classify sources when needed.
7. Write one complete dependency-aware batch.
8. Integrate body links, navigation, metadata, sources, and Expression Layer mapping.
9. Before batch close, build the AuditPlan once and process receipts ([[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]]): complete the `--scope` self-check, the required incremental manual / rendering QA, and the [[kernel/K12 Quality Assurance/14 Batch Review|K12/14]] in-batch items; issue or supersede dimension-specific AuditReceipts and write out the delta; the batch enters `merge-ready`. Visual checks escalate only on a recorded exception trigger.
10. The integrator performs the serial merge ([[kernel/K02 Build Execution/05 Batch Execution|K02/05]] Concurrent Batches): apply the delta, run the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]], verify the K12/14 global items, and update the global Ledger and Amendment Log; batches themselves do not write the global ledger.
11. Close the batch only after Batch Review passes and unresolved invalidations = 0; otherwise it stays active or merge-ready.

Note: Coverage reconciliation is not executed at batch start; reconciliation is executed at batch close.

## Related

- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution Read Set]]
- [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
