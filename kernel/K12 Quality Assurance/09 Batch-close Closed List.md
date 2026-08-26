## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].
- Next: [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Purpose

This module owns the fixed set of deterministic checks run against the merged in-scope snapshot when a batch is closed. It is read by whoever performs the serial merge, and by the Terminal Audit when it runs the same set against the final frozen snapshot. Membership of the list is decided here; which evidence a run may reuse instead of recomputing is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Batch-close Closed List

The exact current membership, stable member IDs, meanings, and order are owned
only by [`batch-close-closed-list.yaml`](batch-close-closed-list.yaml). That
ordered registry is the machine list run against the merged complete in-scope
snapshot when each batch is closed by the integrator during serial merge
(concurrent batches merge one by one, see
[[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|K13/10]]
Concurrent Batches). This prose explains the boundary and does not restate the
machine closed set.

Adding, removing, renaming, or reordering a registry member requires a
governance revision. Every member MUST be implemented by a deterministic
script with a single vault-wide run ≤60 seconds.
[[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
and
[[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
only reference this list and do not list it separately.

These are global invariants that are cheap and easily broken by modifications to other pages. A new result supersedes the previous receipt rather than being treated as meaningless repetition.

The registered `batch-close` producer capability is the sole producer contract
for the close bundle consumed by the Queue close transaction. For one
`merge-ready` batch with an unconsumed canonical Delta-apply receipt, it must
produce evidence for every Closed List member, the selected Profile scan, an
independent review, and the K13/08 consistency Gate against one snapshot. The
consumer validates structure, producer protocol identity, state and snapshot
bindings, and the receipt chain. Generic "QA passed" assertions are invalid;
producer labels alone do not authenticate an executable.

Routed-gap settlement is checked before the expensive Closed List. The
`open -> merge-ready` transition has already projected the frozen Delta over
the live Coverage Ledger and bound a zero-unsettled prospective result; Delta
apply repeats that projection, and the close producer now proves the landed
Coverage still has zero open gaps routed to the closing batch. A mismatch or
nonzero result fails before content checks run. This is the K13/08 lifecycle
precondition, not an additional Closed List member.

Before `registered_residual_content` is invoked, the aggregator MUST resolve
its command from the same current `profile-load` contract admitted for the
selected Profile. A foreign, missing, ambiguous, or otherwise unresolved
Profile-owned dependency fails before a verifier subprocess starts and no
close bundle is published. This use-site resolution is consumption of the one
Profile contract, not an additional Closed List member and not a second
registry parser.

`wiki_link_resolution`, `structural_validity`, and
`graph_and_duplicate_basenames` scan the Git-managed set: tracked files plus
untracked files not excluded by standard Git ignore rules. Tracked files
remain in scope even when an ignore rule matches. An export without Git
metadata scans the filesystem outside control namespaces. Ignored untracked
notes MUST NOT affect these verdicts.

`registered_residual_content` is the only member whose predicate is supplied entirely by the selected profile, so its registered verifier MUST be shown to be live and not merely present. Any registered verifier whose clean result depends on finding no candidate MUST provide executable positive controls that exercise the same production classification path and collectively represent every required structure the verifier claims to recognise. A positive control that is rejected, skipped, or evaluated only by a separate test-only predicate invalidates the run. The verifier owns the representation and schema of its control inputs.

The two Gate objects remain distinct. `profile-load` proves that the selected
Profile, its registration, predicate owners, and Profile-owned configuration
form one authorized dependency closure. `registered-residual-content` proves
what the admitted verifier and configuration found in the scanned repository
snapshot and whether its controls ran. A `config_fingerprint` proves which
configuration bytes executed; by itself it does not prove those bytes belonged
to the selected Profile. Neither Gate substitutes for the other.

The registered scan producer must demonstrate its positive controls through
the same production classifier used for the repository scan. Control and
production results must bind the same Gate meaning, producer protocol, scan
identity, admitted configuration, and exact positive-control set. Missing,
unsupported, failed, empty, mismatched, or contract-divergent control evidence
invalidates the close run. These bindings demonstrate local classifier
behavior; they do not authenticate the executable or prove that the selected
Profile's controls are semantically sufficient.

For the bundled residual-content verifier, the accepted roots provide a repository-backed integration control: when the audited scope contains no candidate, the same configuration MUST still recognise at least one declared-valid object there, and the passing summary MUST name that witness. Its own configuration schema also supplies deterministic synthetic controls for the required heading structures it claims to recognise. A run failing either layer produced no reliable evidence and MUST fail rather than pass. This is an evidence-production failure, not a content finding: `registered_residual_content` still raises content findings only as candidates, and whether the registered controls describe the right structures remains the registering profile's judgment.

`controlled_vocabulary` invokes the `frontmatter-vocabulary` Gate against the
effective composed vocabulary; an absent, empty, unparseable, or fieldless
artifact is not a vocabulary and fails. `structural_validity` applies strict
encoding, frontmatter, fence, and table checks to knowledge Markdown and the
registered restricted-YAML scope; adopter runtime state remains owned by its
own validator.
`graph_and_duplicate_basenames` derives a stable graph projection and basename
candidates from the complete Markdown node set. `wiki_link_resolution` alone
decides whether a link is missing, ambiguous, or has a bad heading; unresolved
projected edges are evidence, not a second verdict. `coverage_file_count`
reconciles the manifest count, Coverage projection, and safe object
materialization; file existence does not prove semantic completeness.
`guidance_and_contract_continuity` proves guidance ID and contract-version
continuity. `manifest_page_contract` applies the `page-contract` Gate to this
batch's manifest pages: the corpus-wide advisory backlog stays advisory, but a
candidate on a manifest page must be fixed or explicitly disposed; a strict
failure on a manifest page fails this member. Where no effective page contract
has been adopted, the member records that it is not applicable rather than
inventing a schema.

A close still performs the complete repository scan. Review disposition,
however, is incremental by exact observation. The immediately preceding
successful close attestation is the sole baseline. A candidate may carry
forward only when that baseline marked it `accept-while-unchanged`, its stable
ID, producer version, and canonical observation hash are identical, and it is
not a manifest-local page-contract finding. A changed producer, changed row,
missing baseline, disappearance followed by reappearance, `accept-current`
disposition, or manifest-local finding makes the candidate fresh. Older
attestations are never searched to bridge a gap in that chain.

The independent reviewer explicitly disposes only the fresh partition, by
stable ID or exact `tool:check` type, and may choose current-only or
while-unchanged acceptance. The new attestation binds the baseline protocol
and receipt, carried and fresh counts, and fingerprints of both exact ID sets;
its accepted total and `candidate_set_sha256` still cover the complete current
set. No prior close or a legacy baseline makes all current candidates fresh.
An unresolvable or malformed current-era latest baseline fails rather than
falling back to an older, more convenient acceptance.

The attestation binds the complete current candidate set, accepted counts and
types, and the exact disposition evidence. Detailed rows may be externalized
once under the registered evidence contract, but their bytes, count, identity,
and content hash remain bound and reverified; externalization cannot weaken or
duplicate the authorization surface. Priority-quota exceptions remain governed
only by K00/07 and the Task Contract and must preserve the security-relevant
decision facts needed for replay. Omitted candidates, unused selectors, or a
reviewer that is not procedurally independent fail. Actor labels remain audit
assertions rather than operating-system authentication.

Every member receipt, reviewer attestation, global review, and aggregate must
bind the same path-sensitive repository snapshot. Unsafe inputs, concurrent or
verifier mutation, and incomplete publication fail closed. The digest detects
stale or inconsistent local evidence; it is not a signature or provenance
attestation. Interrupted publication must remain explicitly recoverable and
cannot appear complete.

Before the integrator records `merge-ready -> closed`, it separately consumes a
current `required-queue-consistency` receipt over Queue, Coverage, and Progress
after the delta. This is not another Closed List member: Required Queue
validation has one canonical Gate at
[[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]].

For a complex batch, the close producer also binds the current Work Spec
identity and fingerprint and verifies its currency around the Closed List.
This is part of the K13/08 Queue consistency contract, not another content
check. A changed or stale Work Spec invalidates the close bundle.

The same close bundle carries the resolved Corpus Planning applicability
decision. When the frozen task selection or affected-path set requires it, the
bundle consumes a distinct current `corpus-plan-structure` child receipt. The
child binds the same task, Queue revisions, state fingerprints, repository
snapshot, and exact Profile and planning-artifact identities. Missing, stale,
aliased, or self-reused child evidence blocks close. This conditional evidence
is not another Closed List content check.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production|Knowledge Batch Production]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
