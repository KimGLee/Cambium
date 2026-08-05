## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]].
- Next: [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]].

## Purpose

This module owns what a task already in flight does when the Standards version it froze at start no longer matches the current one. A selected profile change is a Standards change, always bumps the version, and enters this same procedure. It is read at batch activation by the version self-check, and by a governance revision when that revision closes. It decides the affected scope of a revision; which receipt dimensions a changed rule invalidates is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Active-task Adoption

The **affected scope** of a Standards revision = the receipts and batches corresponding to the changed-predicate list explicitly enumerated in the revision record (which acceptance predicates or gate semantics changed). **Whatever the revision record does not list is not affected.** A revision with no predicate change (wording, version stamp, slimming, comments) takes the no-op path: a byte diff + a one-line adoption receipt completes it, triggering no invalidation and producing no Amendment Record table.

When the Standards version changes and the changed-predicate list is non-empty, active, paused, and completion-candidate tasks MUST:

1. Record the old and new Standards versions and selected profile manifest paths;
2. Re-resolve the selected manifest's slot bindings, vocabulary, supplemental routes, and gates, then re-parse [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]] and the affected gate modules;
3. Determine whether the new rules change the existing Batch/Terminal acceptance predicates;
4. Mark old evidence that cannot satisfy the new receipt schema as `legacy-evidence` rather than forging fingerprints;
5. Allow full receipts to be generated starting from the current batch;
6. Have the Terminal Audit apply risk-targeted re-review to legacy evidence, without requiring indiscriminate rework of closed batches.

Until this adoption is recorded, an affected task cannot activate another batch or enter completion.

## Related

- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|Task Contract Binding and Time Semantics]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
