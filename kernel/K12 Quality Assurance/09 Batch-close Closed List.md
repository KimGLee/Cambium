## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].
- Next: [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]].

## Purpose

This module owns the fixed set of deterministic checks run against the merged in-scope snapshot when a batch is closed. It is read by whoever performs the serial merge, and by the Terminal Audit when it runs the same set against the final frozen snapshot. Membership of the list is decided here; which evidence a run may reuse instead of recomputing is decided by [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]].

## Batch-close Closed List

**Batch-close Closed List**: the following eight items, and only these eight items, run against the merged complete in-scope snapshot when each batch is closed by the integrator during serial merge (concurrent batches merge one by one, see [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|K13/10]] Concurrent Batches) —

1. Wiki link missing / ambiguous / heading resolution (check_links)
2. Markdown / YAML / fence / table structural validity
3. deterministic Markdown/Wiki-link graph JSON projection and duplicate **basename** candidates
4. Coverage file-count reconciliation
5. guidance ID and contract version continuity
6. The batch-close residual-content scan registered in the `Registered Scan Registry`
7. Frontmatter controlled vocabulary validation (`check_vocab`; the active vocabulary is composed from the kernel base and the selected profile's `Vocabulary Extensions`; exclude `kernel/Cards`, whose compiled-artifact integrity is owned by `stamp_cards.py`, not the knowledge-page schema)
8. Page-contract debt on this batch's manifest pages (`check_page_contract`): the corpus-wide advisory backlog stays advisory, but a candidate still carried by a manifest page surfaces as a stable candidate the reviewer must fix or explicitly accept with a recorded disposition, and a strict-mode fail on a manifest page fails the member — legacy debt amortizes batch by batch instead of blocking work that never touched it. Like item 7, the compiled contract exists only where an instance composed it; without `Tools/page_contract.yaml` the member records itself vacuously clean, and composing the contract arms it. Bundles sealed before this member joined the list carry seven members forever under [[kernel/K12 Quality Assurance/10 Standards Version Adoption|K12/10]] producer-era identity.

Adding a new check to this list requires a governance revision, and the check MUST be: a deterministic script, with a single vault-wide run ≤60 seconds. [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]] and [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]] only reference this list and do not list it separately.

These are global invariants that are cheap and easily broken by modifications to other pages. A new result supersedes the previous receipt rather than being treated as meaningless repetition.

`Tools/check_batch_close.py` is the sole supported producer contract for the close bundle consumed by `Tools/update_queue.py`. For one `merge-ready` batch with an unconsumed canonical Delta-apply receipt, it holds the shared writer lock, runs all Closed List members, the profile's single item-6 scan, an independent review, and the K13/08 consistency gate, then returns the three receipt IDs needed to close. The consumer validates the expected structure, declared producer/version labels, state and snapshot bindings, and receipt chain; generic "QA passed" assertions or records that do not satisfy that contract are invalid. The labels themselves do not authenticate which executable emitted the bytes.

Routed-gap settlement is checked before the expensive Closed List. The
`open -> merge-ready` transition has already projected the frozen Delta over
the live Coverage Ledger and bound a zero-unsettled prospective result; Delta
apply repeats that projection, and the close producer now proves the landed
Coverage still has zero open gaps routed to the closing batch. A mismatch or
nonzero result fails before content checks run. This is the K13/08 lifecycle
precondition, not a ninth Closed List member.

Before item 6 is invoked, the aggregator MUST resolve its command from the
same current `profile-load` contract admitted for the selected Profile. A
foreign, missing, ambiguous, or otherwise unresolved Profile-owned dependency
fails before a verifier subprocess starts and no close bundle is published.
This use-site resolution is consumption of the one Profile contract, not a
ninth Closed List member and not a second registry parser.

Items 1 through 3 scan the Git-managed set: tracked files plus untracked files
not excluded by standard Git ignore rules. Tracked files remain in scope even
when an ignore rule matches. An export without Git metadata scans the
filesystem outside control namespaces. Ignored untracked notes MUST NOT affect
these verdicts.

Item 6 is the only member whose predicate is supplied entirely by the selected profile, so its registered verifier MUST be shown to be live and not merely present. Any registered verifier whose clean result depends on finding no candidate MUST provide executable positive controls that exercise the same production classification path and collectively represent every required structure the verifier claims to recognise. A positive control that is rejected, skipped, or evaluated only by a separate test-only predicate invalidates the run. The verifier owns the representation and schema of its control inputs.

The two Gate objects remain distinct. `profile-load` proves that the selected
Profile, its registration, predicate owners, and Profile-owned configuration
form one authorized dependency closure. `registered-residual-content` proves
what the admitted verifier and configuration found in the scanned repository
snapshot and whether its controls ran. A `config_fingerprint` proves which
configuration bytes executed; by itself it does not prove those bytes belonged
to the selected Profile. Neither Gate substitutes for the other.

The invocation protocol is shared. `check_batch_close.py` first invokes the same registered verifier command with the additional standard flag `--positive-controls-only`, then invokes the registered production command unchanged. The control invocation MUST execute the registered controls through the production classifier without scanning repository content; the production invocation MUST execute those controls again before its one vault-wide scan. Each reliable invocation MUST finish with one passing summary. The two final summaries MUST use the same `check` meaning and agree exactly on `tool`, `tool_version`, `check`, `scan_id`, `config_fingerprint`, `positive_control_result: passed`, `positive_control_mode: production-classifier`, a positive integer `positive_control_count`, and a `sha256:<64 lowercase hex>` `positive_control_fingerprint` over the exact control set. Agreement is not self-authorization: each summary's `scan_id` MUST equal the stable ID in the admitted Registered Scan row, and when that row declares an explicit Profile-owned config, each `config_fingerprint` MUST equal the SHA-256 of those admitted config bytes. An absent, unsupported, failed, non-final, empty, mismatched, or contract-divergent control invocation invalidates the close run. These fields and the second invocation prove only what the registered executable asserted and demonstrated locally; they do not authenticate the executable or make the Profile's chosen controls semantically sufficient.

For the bundled residual-content verifier, the accepted roots provide a repository-backed integration control: when the audited scope contains no candidate, the same configuration MUST still recognise at least one declared-valid object there, and the passing summary MUST name that witness. Its own configuration schema also supplies deterministic synthetic controls for the required heading structures it claims to recognise. A run failing either layer produced no reliable evidence and MUST fail rather than pass. This is an evidence-production failure, not a content finding: item 6 still raises content findings only as candidates, and whether the registered controls describe the right structures remains the registering profile's judgment.

Item 7 validates against the composed artifact, so one that is absent, empty, unparseable, or carrying no field set is not a vocabulary: the item MUST fail rather than report no unknown value. Item 2 applies strict UTF-8, frontmatter, fence, and table checks to Markdown. Its restricted YAML check covers only kernel, profile, and composed-vocabulary YAML; `check_queue.py` separately parses `.cambium`, and unrelated adopter YAML is out of scope. Item 3 deterministically derives an in-memory JSON projection from the complete Markdown node set and its Wiki links, records resolved and unresolved edges in stable order, proves a canonical JSON round-trip, and reports duplicate Markdown basenames as candidates. Item 1 alone decides whether a link is missing, ambiguous, or has a bad heading; unresolved edges in the projection are evidence, not a second link verdict. Ordinary repository JSON and fenced JSON examples are not graph artifacts and are not scanned by item 3. Item 4 reconciles the batch manifest count, Coverage projection, and safe object materialization; file existence does not prove semantic completeness.

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

The attestation carries the authorization surface inline in compact form: the accepted count, the accepted types with per-type counts, and a `candidate_set_sha256` fingerprint over the sorted accepted candidate IDs. The full disposition detail — every accepted row with its member, target, details, acceptance path, observation hash, and current-only or while-unchanged disposition — is written exactly once per close attempt as a born-cold evidence file under `.cambium/receipts/cold/close-evidence/`, which the attestation binds by path, byte size, record count, and content hash; the member receipts and any failure receipt bind the same externalized evidence instead of repeating it. The hot catalog never re-deserializes that detail, but every consistency run MUST compare the file's actual bytes against the hash the attestation bound, not merely its length: a same-length edit to an acceptance row would otherwise pass, and the next seal would hash the edited bytes into the cold manifest and make the edit permanent evidence — laundering a tamper through the very mechanism that exists to freeze history. A seal MUST therefore refuse to adopt any evidence file that no current attestation binds, or whose bytes do not match the hash it binds ([[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]] owns the cold chain). The incident behind this shape: a close register that repeated two-thousand-row candidate detail three times per attempt grew past sixty megabytes and priced every later state transition out of its execution channel. One carve-out this list does not own: a priority-quota candidate cannot be accepted by either selector. It is consumed only through a currently valid bounded policy exception in the Task Contract ([[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|K00/07]] owns the instruments; [[kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics|K13/02]] the register), the disposition seals the decision facts -- decision ID, bound, scope, effective-policy fingerprint, and the exact counts -- and stays INLINE in the attestation rather than in the externalized evidence file, because it is the security-relevant authorization record a replay validates field by field; it replays as history even after the exception is revoked, so revocation never orphans a sealed close. Unused selectors, omitted current candidates, or equal integrator and reviewer labels fail. The labels and attestation are audit assertions: the local baseline does not authenticate an operating-system principal, prove that two labels name different people or processes, or prove that the stated review occurred. Actual reviewer independence remains a procedural requirement supplied by the operator or by an externally controlled execution system.

The seven member receipts, reviewer attestation, global review, and aggregator MUST bind the same `merged_snapshot_sha256`: a path-sensitive digest of regular files outside root `.git/` and `.cambium/`. The tool recomputes it around checks and publication; K13/08 computes its own value; the close writer checks the current bytes under lock. Unsafe file types, concurrent or verifier mutation, and incomplete publication fail. This digest detects stale or inconsistent local evidence; it is not a signature or provenance attestation. If append completion is uncertain, the lock remains so the next Agent discovers the interrupted transaction through `check_queue.py --resume-status`.

Before the integrator records `merge-ready -> closed`, it separately consumes a current `Tools/check_queue.py` receipt recording a passed Queue/Coverage/Progress consistency check after the delta. This is not an eighth Closed List item: Required Queue validation has one canonical gate at [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]], while the seven items above own merged content-snapshot invariants.

For a complex batch, `Tools/check_batch_close.py` also binds the current Work
Spec path/hash into its close bundle and verifies the bytes before and after
the Closed List. This is part of the K13/08 Queue consistency contract, not an
eighth content check. A changed or stale Work Spec invalidates the close bundle
even when all seven content checks passed.

The same close bundle carries an explicit Corpus Planning applicability
decision. It requires a distinct current `check_corpus_plan.py` child receipt
when the task selected R13 or the batch manifest intersects the selected Profile Scope or slot,
one of the three bound artifacts, a Global Map Entry path, a Matrix
canonical/evidence path, or a Gap promoted/evidence path. These are normalized
paths parsed by the validator; no semantic inference expands the set. The
aggregator records `corpus_plan_required`, the sorted trigger set, and the
child receipt ID or null. R13 requires a configured plan. The child binds the
same task, Queue revisions, state fingerprints, and merged repository snapshot
as the close bundle, plus exact Profile/slot/artifact fingerprints. A missing,
stale, aliased, or self-reused child blocks close. This conditional evidence is
not an eighth Closed List content check.

## Related

- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production|Knowledge Batch Production]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]]
