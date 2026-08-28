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

The sole machine list for an ordinary batch's changed-scope obligations is [`changed-scope-check-registry.yaml`](changed-scope-check-registry.yaml). Its rows freeze applicability, producer, evidence, dimension, consumer, and due stage. These bullets explain boundaries only: omitted prose does not remove a row, and prose absent from the registry is not an AuditPlan obligation.

Candidate rows can open review scope but cannot fail it directly. Maintenance, Standards-governance, and Terminal checks stay outside this base. Profile checks enter only through `k12-05-registered-scan` and remain Profile-owned.

- Empty- and short-file scans produce candidates only; a Tool cannot invent a threshold, unit, or applicable page set.
- Missing Sources, Related, and metadata belong to the advisory `page-contract` Gate under [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]]. Missing `Related` is not reported ([[kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation|K09/04]]), while claim support remains [[kernel/K07 Sources and Accuracy Standard|K07]] review.
- Frontmatter controlled vocabulary validation is performed by the
  `frontmatter-vocabulary` Gate over the Kernel base vocabulary and selected
  Profile extensions. The vault-wide run at batch close is item 7 of the
  [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]];
  here only the changed-scope self-check is done.
- Candidate scans for the `Language Contract` or other profile contracts are activated by the admitted selected Profile's `Registered Scan Registry`; the kernel only requires that a scan declare its scope, candidate boundary, and acceptance owner. Registry and Profile-owned dependency resolution belongs to `profile-load`; the candidate scan consumes that contract and does not recreate it.
- Template fields become required only through the K08 applicability contract; evidence/claim/page-type consistency remains semantic review unless an exact predicate is registered.
- Consistency checks across Standard Module MOCs, leaf modules, and registered
  navigation targets. The `standards-moc-consistency` candidate scan runs only
  in maintenance and Standards-governance tasks, not batch checks.
- Standards-migration conservation is not inferred for ordinary batches.
- Machine-checkable references frozen by the Task Contract are validated by
  the capability registered for their canonical component contract. Profile
  manifest identity and its typed dependency closure are validated separately
  by the `profile-load` Gate; resolving that closure does not prove that an
  unrelated loading or delivery obligation was fulfilled.
- Rendering follows [[kernel/K12 Quality Assurance/02 Rendering Verification|K12/02]]: only its admitted predicates enter the base, its dimensions stay distinct, and its mode record does not prove those predicates passed.
- Cross-file duplicate-block detection is a registered candidate capability;
  semantic review decides whether similar paragraphs violate the
  [[kernel/K00 Standards Control/11 Standards Map and Rule Registry#Cross-domain Rule Registry|Cross-domain Rule Registry]].
  It runs only in maintenance and governance tasks; batch close retains only
  the basename candidate member.
- `terminal-proof` validates Terminal Proof completeness and zero-value
  conditions under the contract in K12/16, reconciling the frozen Standards,
  selected Profile, runtime state, and remaining Required gaps.
- `knowledge-freshness` computes `review_by` only from a temporally valid
  baseline and resolved volatility, and emits the complete maintenance
  candidate set. Freshness semantics and closed-world pass are owned by
  [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|K08/05]];
  fusion and budget order are owned by
  [[kernel/K00 Standards Control/08 Maintenance Run Envelope|K00/08]].

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
