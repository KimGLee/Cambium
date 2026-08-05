## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].
- Next: [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Purpose

This module owns the fixed set of deterministic checks run against the merged in-scope snapshot when a batch is closed. It is read by whoever performs the serial merge, and by the Terminal Audit when it runs the same set against the final frozen snapshot. Membership of the list is decided here; which evidence a run may reuse instead of recomputing is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Batch-close Closed List

**Batch-close Closed List**: the following seven items, and only these seven items, run against the merged complete in-scope snapshot when each batch is closed by the integrator during serial merge (concurrent batches merge one by one, see [[kernel/K02 Build Execution/05 Batch Execution|K02/05]] Concurrent Batches) —

1. Wiki link missing / ambiguous / heading resolution (check_links)
2. Markdown / YAML / fence / table structural validity
3. deterministic Markdown/Wiki-link graph JSON projection and duplicate **basename** candidates
4. Coverage file-count reconciliation
5. guidance ID and contract version continuity
6. The batch-close residual-content scan registered in the `Registered Scan Registry`
7. Frontmatter controlled vocabulary validation (`check_vocab`; the active vocabulary is composed from the kernel base and the selected profile's `Vocabulary Extensions`; exclude `kernel/Cards`, whose compiled-artifact integrity is owned by `stamp_cards.py`, not the knowledge-page schema)

Adding a new check to this list requires a governance revision, and the check MUST be: a deterministic script, with a single vault-wide run ≤60 seconds. [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]] and [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]] only reference this list and do not list it separately.

These are global invariants that are cheap and easily broken by modifications to other pages. A new result supersedes the previous receipt rather than being treated as meaningless repetition.

`Tools/check_batch_close.py` is the sole supported producer contract for the close bundle consumed by `Tools/update_queue.py`. For one `merge-ready` batch with an unconsumed canonical Delta-apply receipt, it holds the shared writer lock, runs all seven members, the profile's single item-6 scan, an independent review, and the K02/09 consistency gate, then returns the three receipt IDs needed to close. The consumer validates the expected structure, declared producer/version labels, state and snapshot bindings, and receipt chain; generic "QA passed" assertions or records that do not satisfy that contract are invalid. The labels themselves do not authenticate which executable emitted the bytes.

Item 2 applies strict UTF-8, frontmatter, fence, and table checks to Markdown. Its restricted YAML check covers only kernel, profile, and composed-vocabulary YAML; `check_queue.py` separately parses `.cambium`, and unrelated adopter YAML is out of scope. Item 3 deterministically derives an in-memory JSON projection from the complete Markdown node set and its Wiki links, records resolved and unresolved edges in stable order, proves a canonical JSON round-trip, and reports duplicate Markdown basenames as candidates. Item 1 alone decides whether a link is missing, ambiguous, or has a bad heading; unresolved edges in the projection are evidence, not a second link verdict. Ordinary repository JSON and fenced JSON examples are not graph artifacts and are not scanned by item 3. Item 4 reconciles the batch manifest count, Coverage projection, and safe object materialization; file existence does not prove semantic completeness.

A candidate is accepted only by its stable ID or exact `tool:check` type in the independent review attestation. Unused selectors, omitted current candidates, or equal integrator and reviewer labels fail. The labels and attestation are audit assertions: the local baseline does not authenticate an operating-system principal, prove that two labels name different people or processes, or prove that the stated review occurred. Actual reviewer independence remains a procedural requirement supplied by the operator or by an externally controlled execution system.

The seven member receipts, reviewer attestation, global review, and aggregator MUST bind the same `merged_snapshot_sha256`: a path-sensitive digest of regular files outside root `.git/` and `.cambium/`. The tool recomputes it around checks and publication; K02/09 computes its own value; the close writer checks the current bytes under lock. Unsafe file types, concurrent or verifier mutation, and incomplete publication fail. This digest detects stale or inconsistent local evidence; it is not a signature or provenance attestation. If append completion is uncertain, the lock remains so the next Agent discovers the interrupted transaction through `check_queue.py --resume-status`.

Before the integrator records `merge-ready -> closed`, it separately consumes a current `Tools/check_queue.py` receipt recording a passed Queue/Coverage/Progress consistency check after the delta. This is not an eighth Closed List item: Required Queue validation has one canonical gate at [[kernel/K02 Build Execution/09 Required Queue|K02/09]], while the seven items above own merged content-snapshot invariants.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
