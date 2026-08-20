## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/04 Guidance and Source Review|Guidance and Source Review]].
- Next: [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]].

## Automated Checks

Each batch of work generates an AuditPlan before batch close per [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]. The full checks at batch close are governed by the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; this page does not list them separately.

## Codification Admission

This section owns the criterion for which side of this page's boundary a rule falls on. A rule MAY be carried by a deterministic check when four questions all answer yes, and only then:

1. The judgment depends only on sets, existence, equality, order, counts, or format — never on semantic understanding.
2. The inputs are deterministically readable bytes inside the repository.
3. The output is pass / fail / candidate with a locatable position.
4. The same input always produces the same output.

Any answer of no leaves the rule in the semantic layer, judged by a person or an agent under review discipline. Once all four answer yes, codification is the DEFAULT, not an option: a coded invariant cannot drift back, while a prose invariant is re-judged by every executor that reads it, and each re-judgment is a chance to diverge. Semantic review then carries only what determinism cannot express.

A deterministic check judges; it never adjudicates. It may report that two records disagree; it does not decide which is authoritative, whether a boundary was crossed, or whether a compression is faithful — those verdicts stay with review and carry review evidence. The following MUST NOT be disguised as deterministic checks, whatever their prompt or threshold dressing: whether a source actually supports a claim; whether a canonical owner, responsibility boundary, or split granularity is semantically right; whether two concepts are synonymous, inclusive, conflicting, or merely similar; whether a conclusion is stable enough for promotion; whether structure, summary, evidence quality, or content depth meets substantive acceptance.

An admitted check enters through the [[kernel/K00 Standards Control/12 Control Registry#Stable Gate ID Registry|Control Registry]] with a Gate ID, producer, and consumer, or it is a second truth source rather than a control. The kernel leaf owns the rule first; a judgment rule that exists only as a constant inside a tool is unowned, and the tool never invents semantics its owner never stated.

## Domain-specific Checks

The following domain-specific check items run only on the changed / invalidated scope:

- `unclassified_guidance`, `accepted_unmapped_guidance`, and `implemented_unverified_guidance` checks.
- Checks for `unassessed`, Required gaps with no next batch, and deferred/excluded without a reason.
- Checks for empty files and extremely short core/process/system files; results serve only as review candidates and do not fail automatically.
- Missing Sources, Related, and metadata checks run as the advisory `page-contract` gate owned by [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]]; a missing `Related` is never reported ([[kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation|K09/04]]), and claim support stays with [[kernel/K07 Sources and Accuracy Standard|K07]] review below — never a second sources tool. Checks of profile-owned expression links, extension metadata, or other profile predicates are registered by the `Registered Scan Registry`; the kernel does not name concrete implementations.
- Frontmatter controlled vocabulary validation is performed by `check_vocab`; its input MUST be composed from the kernel base vocabulary and the selected profile's `Vocabulary Extensions`. The vault-wide run at batch close is item 7 of the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; here only the changed-scope self-check is done.
- Candidate scans for the `Language Contract` or other profile contracts are activated by the admitted selected Profile's `Registered Scan Registry`; the kernel only requires that a scan declare its scope, candidate boundary, and acceptance owner. Registry and Profile-owned dependency resolution belongs to `profile-load`; the candidate scan consumes that contract and does not recreate it.
- Checks for Source Notes missing source URL, date, evidence role, or affected notes.
- Checks for Research Synthesis missing source set, disagreement, or graph decision.
- Consistency checks between `evidence_maturity` and source-driven page types.
- Consistency checks across Standard Module MOCs, leaf modules, and Read Set targets — the consistency of the MOC Module Index with the actual H2 headings is implemented as `Tools/check_moc.py` (candidates only); run in maintenance runs and governance tasks, not in batch checks.
- Checks in Standards migration for owner uniqueness, omission, and duplication of the original content blocks.
- Resolvability checks for selected Rxx route IDs and Runtime Card paths, Read Sets actually read back, any combined namespaced profile route, the loaded set, Standards version, and selected profile manifest in the Task Contract. The manifest and its typed Profile dependency closure are the separate `profile-load` Gate; closure members do not enter `loaded_module_paths` merely because the Profile linker resolved them.
- Mermaid compile, asset path, deterministic rendering evidence, and `rendering_mode` enumeration checks.
- Level 2–4 records MUST include visual trigger, unresolved question, target, and result; a batch without a trigger requires no visual evidence.
- Cross-file duplicate block detection — run a paragraph-level similarity scan with `Tools/duplicate_check.py`; similar paragraph pairs are reported as candidates, with manual judgment on whether they violate the [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]]. Run only in maintenance runs and governance tasks; at the batch level only the basename-level detection in the Closed List is kept.
- Terminal Proof completeness and zero-value condition validation (canonical definition in [[kernel/K12 Quality Assurance/16 Terminal Proof Contract#Terminal Proof Contract|Terminal Proof Contract]]) — implemented as `Tools/check_proof.py`; terminal mode reconciles the frozen Standards version and selected profile against the active K00/03 state and Progress Ledger, and MUST reconcile Required gaps with the current Coverage Ledger.
- Knowledge freshness check — `Tools/check_freshness.py` computes `review_by` only from a temporally valid baseline and resolved volatility, and outputs the complete freshness candidate set for maintenance runs. That set is not limited to overdue pages: it preserves content-modified-since-review, awaiting-first-verification, invalid or future explicit event, invalid or unresolved volatility, and unparseable-frontmatter candidates. Maintenance-run only; not run in batch checks. Freshness semantics and the closed-world pass rule are owned by [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]; fusion and budget order are owned by [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]].

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
