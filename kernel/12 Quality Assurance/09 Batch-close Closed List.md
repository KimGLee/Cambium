## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].
- Next: [[kernel/12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Purpose

This module owns the fixed set of deterministic checks run against the merged in-scope snapshot when a batch is closed. It is read by whoever performs the serial merge, and by the Terminal Audit when it runs the same set against the final frozen snapshot. Membership of the list is decided here; which evidence a run may reuse instead of recomputing is decided by [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Batch-close Closed List

**Batch-close Closed List**: the following seven items, and only these seven items, run against the merged complete in-scope snapshot when each batch is closed by the integrator during serial merge (concurrent batches merge one by one, see [[kernel/02 Build Execution/05 Batch Execution|02/05]] Concurrent Batches) —

1. Wiki link missing / ambiguous / heading resolution (check_links)
2. Markdown / YAML / fence / table structural validity
3. graph JSON and duplicate **basename** candidates
4. Coverage file-count reconciliation
5. guidance ID and contract version continuity
6. The batch-close residual-content scan registered in the `Registered Scan Registry`
7. Frontmatter controlled vocabulary validation (check_vocab; the active vocabulary is composed from the kernel base and the selected profile's `Vocabulary Extensions`)

Adding a new check to this list requires a governance revision, and the check MUST be: a deterministic script, with a single vault-wide run ≤60 seconds. [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]] and [[kernel/12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]] only reference this list and do not list it separately.

These are global invariants that are cheap and easily broken by modifications to other pages. A new result supersedes the previous receipt rather than being treated as meaningless repetition.

## Related

- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/02 Build Execution/05 Batch Execution|Batch Execution]]
- [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]]
