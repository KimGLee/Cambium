## Navigation

- Parent: [[kernel/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[kernel/12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].
- Next: [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]].

## Automated Checks

Each batch of work generates an AuditPlan before batch close per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]. The full checks at batch close are governed by the [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]]; this page does not list them separately.

## Domain-specific Checks

The following domain-specific check items run only on the changed / invalidated scope:

- `unclassified_guidance`, `accepted_unmapped_guidance`, and `implemented_unverified_guidance` checks.
- Checks for `unassessed`, Required gaps with no next batch, and deferred/excluded without a reason.
- Checks for empty files and extremely short core/process/system files; results serve only as review candidates and do not fail automatically.
- Checks for missing Sources, Related, and metadata. Checks of profile-owned expression links, extension metadata, or other profile predicates are registered by the `Registered Scan Registry`; the kernel does not name concrete implementations.
- Frontmatter controlled vocabulary validation is performed by `check_vocab`; its input MUST be composed from the kernel base vocabulary and the selected profile's `Vocabulary Extensions`. The vault-wide run at batch close is item 7 of the [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Batch-close Closed List]]; here only the changed-scope self-check is done.
- Candidate scans for the `Language Contract` or other profile contracts are activated by the `Registered Scan Registry`; the kernel only requires that a scan declare its scope, candidate boundary, and acceptance owner.
- Checks for Source Notes missing source URL, date, evidence role, or affected notes.
- Checks for Research Synthesis missing source set, disagreement, or graph decision.
- Consistency checks between `evidence_maturity` and source-driven page types.
- Consistency checks across Standards domain MOC, leaf modules, and Read Set targets — the consistency of the MOC Module Index with the actual H2 headings is implemented as `Tools/check_moc.py` (candidates only); run in maintenance runs and governance tasks, not in batch checks.
- Checks in Standards migration for owner uniqueness, omission, and duplication of the original content blocks.
- Resolvability checks for the selected runtime guidance, Read Sets, loaded set, and Standards version in the Task Contract.
- Mermaid compile, asset path, deterministic rendering evidence, and `rendering_mode` enumeration checks.
- Level 2–4 records MUST include visual trigger, unresolved question, target, and result; a batch without a trigger requires no visual evidence.
- Cross-file duplicate block detection — run a paragraph-level similarity scan with `Tools/duplicate_check.py`; similar paragraph pairs are reported as candidates, with manual judgment on whether they violate the [[kernel/00 Standards Control/05 Core Principles and Standards Map#Cross-domain Rule Registry|Cross-domain Rule Registry]]. Run only in maintenance runs and governance tasks; at the batch level only the basename-level detection in the Closed List is kept.
- Terminal Proof completeness and zero-value condition validation (canonical definition in [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report#Terminal Audit|Terminal Audit]]) — implemented as `Tools/check_proof.py`, able to cross-reconcile with the Coverage Ledger.
- Knowledge freshness check — `Tools/check_freshness.py` computes review_by from volatility and last_verified, and outputs an overdue list (sorted by priority) as candidate input for maintenance runs. Maintenance-run only; not run in batch checks. For the rule owner see [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]].

Profile-registered automated checks may produce results only within their registered candidate boundary and acceptance predicate; candidate scans MUST NOT fail items directly. No automated check can replace content review.

## Manual Checks

Manual or model review covers changed, invalidated, and bounded-sampling objects; all previously passed pages MUST NOT be redone indiscriminately merely because the next audit layer is entered. P0/P1 pages do not stay permanently in manual review scope because of priority; their long-term assurance is carried by freshness-expiry re-verification. Judgment is needed on:

- Whether the causal chain holds.
- Whether the examples really illustrate the mechanism.
- Whether the comparison dimensions are fair.
- Whether the failure modes are concrete.
- Whether the content contains duplication or hollow padding.
- Whether the page can withstand further questioning.
- Whether the current topic remains focused.
- Whether the profile-specific manual dimensions registered in the `Audit Dimension Registry` are accepted by their canonical acceptance owners.
- Whether external sources genuinely change or reinforce knowledge rather than only adding summary files.
- Whether the selected `Profile Scope`'s content mainline and foundational knowledge completeness both hold.
- Whether Process / Flow pages include decision, branch, loop, state mutation, external effect, failure, and terminal condition.
- Whether visual escalation truly stems from a specific display uncertainty that deterministic evidence cannot eliminate, rather than opening the UI by default because a new visual construct was added.
- Whether Levels 2–4 check only the minimal pages, regions, viewports, or action sequences needed to resolve the unresolved question; whether, absent a trigger, the work correctly stops at Level 0 / Level 1.
- Whether UI, screenshots, or screen recordings are wrongly used to prove body text, links, formula semantics, sources, or coverage.
- Whether user guidance is correctly understood, bounded, and scheduled, rather than omitted, over-expanded, or downgraded.
- Whether guidance-caused interruptions occur at safe boundaries and preserve a recoverable checkpoint.

Every manual conclusion MUST be bound to a concrete scope, rubric/acceptance predicate, artifact/dependency fingerprints, and evidence reference. When sampling finds a reproducible problem, the affected family MUST be defined first, then the scope expanded within bounds; local failures MUST NOT be silently left to the Terminal Audit.
