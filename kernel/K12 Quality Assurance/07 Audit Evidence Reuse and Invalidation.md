## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]].
- Next: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

## Purpose

This module specifies how verification evidence is reused across single pages, batches, modules, specialized audits, and the Terminal Audit, with protocol rules that prevent later modifications from silently inheriting old results inside the declared trust boundary. The goal is not to reduce quality dimensions but to eliminate two errors:

1. Every layer repeating expensive manual review from scratch, wasting execution time and context;
2. Continuing to rely on an old conclusion after content, dependencies, or rules have changed, merely because a page once passed.

The core chain: changed objects and acceptance predicates generate a dimension-specific AuditPlan, which produces append-only AuditReceipt records carrying dependency / contract fingerprints; receipts are reusable while predicates and fingerprints remain valid, relevant changes trigger invalidation, bounded expansion applies when local failures show systemic impact, and finally Terminal reconciliation runs on the frozen snapshot. Append-only and immutable mean protocol-level history preservation, not cryptographic tamper resistance.

The `AuditPlan` a batch generates from this decision, and the checks that are incremental by default, are owned by [[kernel/K12 Quality Assurance/19 Incremental Audit Planning|Incremental Audit Planning]].

## Audit Layers

Each layer owns different questions; identical work must not be hidden behind different names:

| Layer | Owns | Reuses | Must not do |
|---|---|---|---|
| Single Note Review | One page's type-aware content, source, link, and rendering quality under the current version | Valid receipts for the same page's unaffected dimensions | Declare a module or the whole vault complete |
| Batch Review | This batch's Required objects, integration edges, and control-plane closure | Prerequisite receipts still valid before this batch started | Unconditionally re-review all historical pages |
| Module Review | owner completeness, dependency continuity, duplicate/orphan, and entry consistency | Valid local receipts of closed batches | Equate local passes with module completeness |
| Specialized Audit | Cross-batch source, case, migration, currentness, or profile invariants registered in the `Routing And Gate Registry` | Passed local content receipts | Redo page-by-page content review unrelated to the specialized invariant |
| Terminal Audit | The final frozen snapshot's scope, guidance, coverage, global invariants, and proof | All still-valid receipts and batch evidence | Blindly trust historical status or indiscriminately redo all manual review |

The same invariant MAY be reconfirmed at multiple layers, but each time the new audit object must be stated. For example, the Batch link check proves the graph still resolves after this batch's writes; the Terminal full-vault link check proves the final snapshot was not broken by subsequent batches.

## Dimension-specific Audit Receipt

Audit evidence is stored per dimension; recording only a vague `reviewed: true` is not allowed. The kernel fixes the following seven base dimensions:

```text
structure_and_links
content_and_depth
formula_and_numeric
source_and_currentness
coverage_and_integration
rendering
guidance_and_contract
```

The `Audit Dimension Registry` MAY append profile-owned dimensions, but MUST NOT delete, rename, or redefine the seven base dimensions above. Its append unit is a judgment item, not a dimension name, and the declarations it MUST carry are fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Profile Registration|K12/08]].

Which dimension a kernel judgment item files its verdict under, and whether it emits a receipt at all, is fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Item Map|K12/08]]; an item that consumes evidence produced elsewhere does not open a second receipt for the same audit object.

One verification produces one append-only `AuditReceipt` protocol record, for example:

```yaml
receipt_id: audit-<stable-id>
dimension: structure_and_links
scope: ["<audited path or snapshot>"]
acceptance_predicate: "missing=0 AND ambiguous=0"
artifact_fingerprint: "sha256:..."
dependency_fingerprint: "sha256:..."
contract_fingerprint: "sha256:..."
standards_version: "<active-instance-standards-version>"
verifier: {name: "kb-audit", version: "..."}
method: deterministic-full
result: passed
evidence_ref: "..."
created_at: "..."
review_due:
supersedes:
```

Field semantics:

- `scope`: the pages, module, batch, or vault-wide snapshot the receipt actually covers.
- `acceptance_predicate`: the specific condition evaluated against the recorded scope and bytes; writing only `QA passed` is not allowed.
- `artifact_fingerprint`: covers body content, file path, and the frontmatter fields `type`, `priority`, `tier`, `coverage_disposition`, `lifecycle`, `prerequisites`. **Explicitly excluded**: `authoring_status`, `learning_status`, the readiness statuses registered by the selected `Vocabulary Extensions`, and `last_reviewed`, `last_verified`, `review_by`, `next_batch` — write-backs of status axes and scheduling fields **do not invalidate the receipt**.
- `dependency_fingerprint`: the canonical owners, sources, schemas, MOC, or configuration this dimension depends on.
- `contract_fingerprint`: the relevant control state such as scope, acceptance, exclusions, and queue/guidance cutoff.
- `verifier` / `method`: the declared producer label and version of the script, compiler, manual rubric, or model review; these fields do not authenticate an actor.
- `evidence_ref`: the location of the command result, review record, compiled artifact, or Batch Review evidence.
- `review_due`: when time-sensitive facts need re-verification; stable mechanisms MAY leave it empty.

`last_reviewed`, `last_verified`, file length, or `authoring_status` cannot substitute for an AuditReceipt.

The canonical receipt format is JSONL (schema in `Tools/schemas/receipt.template.jsonl`). Receipts for deterministic checks are emitted automatically by `Tools/check_*.py` via the `--receipts` parameter; receipts for manual checks are hand-recorded to the same schema. A script-level receipt is a lightweight layer; when it enters the Audit Receipt Register, the AuditPlan layer completes the full AuditReceipt fields of this section, with the script `receipt_id` as the `evidence_ref`.

Receipts are stored by default in the Batch Contract, the Audit Report, or a separately managed index; the Coverage Ledger only needs to record the affected objects' latest valid receipt IDs and invalidation state, and complete receipts are not required to be copied into every knowledge page.

## Reuse Gate

A historical receipt is reusable only when all of the following hold:

```text
receipt.result = passed
AND current_scope is contained in receipt.scope
AND acceptance_predicate is unchanged or weaker
AND artifact_fingerprint matches
AND relevant dependency_fingerprint matches
AND contract_fingerprint matches the audited dimension
AND verifier remains accepted
AND review_due is empty or not reached
AND no applicable invalidation event exists
```

Reuse MUST record `reused_receipt_id` and the reuse rationale; writing only "checked previously" is not allowed. When a single batch reuses ≤10 receipts, the reuse rationale MAY be declared once for the whole batch. Partial reuse by dimension is allowed: for example, when the body is unchanged but new incoming links were added, `content_and_depth` remains valid while `structure_and_links` and `coverage_and_integration` are recomputed.

The following cases SHOULD NOT trigger re-review of unrelated dimensions:

- A modification in another independent module;
- Updating only the prose description in the Progress Ledger;
- A formatting fix that does not change a claim SHOULD NOT automatically invalidate source review;
- A link fix that does not change the body or the host contract SHOULD NOT automatically trigger visual recognition.

## Invalidation

### Direct Invalidation

The following changes invalidate the corresponding receipt:

- A change to an in-scope file's content, path, or the fields covered by `artifact_fingerprint` (write-backs to the excluded fields do not invalidate; see field semantics);
- A change to the acceptance predicate, note type, priority, or Required disposition;
- An incompatible change of verifier or parser/compiler version;
- `review_due` expiry;
- New evidence directly overturning or restricting a reviewed claim;
- A user correction or accepted guidance changing the reviewed semantics;
- The audit itself finding the receipt's input incomplete or its result wrong.

### Dependency Invalidation

Propagation goes only to the dimensions that genuinely depend on the change:

| Changed dependency | Normally invalidates |
|---|---|
| canonical prerequisite mechanism | content/integration of dependent claims |
| Source Note or official current contract | source/currentness and dependent claims |
| expression artifacts registered by the `Expression Layer Entry` | the R05 structure/link, source/currentness, coverage/integration, content/depth, and guidance/contract dimensions actually affected, plus any profile extension dimension registered for the artifact |
| path, heading or alias | structure/link and navigation integration |
| MOC, Coverage or Required Queue | coverage/integration and contract reconciliation |
| formula convention or metric denominator | formula/numeric and dependent evaluation claims |
| `Language Contract` | the content dimension registered in the `Audit Dimension Registry`; if headings, paths, or aliases change, additionally invalidate structure/link and integration |
| theme, plugin or rendering contract | rendering receipts for affected constructs only |
| Standards gate semantics | receipts whose acceptance predicate became stricter or different |

The dependency graph is not required to treat every backlink as a semantic dependency. Prerequisites in the body, claim evidence, canonical ownership, profile-registered expression mapping, MOC membership, and contract mapping are the primary invalidation edges.

A `profile-load` receipt is reusable only for its exact manifest, Profile
directory snapshot, and typed Profile-contract fingerprint. A change to the
manifest, a bound slot, a registered command, a Profile-owned configuration,
a predicate-owner path or heading, or the `check_profile` contract invalidates
that pass. The closure cannot be transferred to another Profile even when the
foreign target has identical bytes. Because a passing closure contains every
Profile-owned target inside one directory, the Profile snapshot covers the
target bytes; the contract fingerprint separately covers the edge kind,
owner identity, canonical target, and optional heading.

Downstream invalidation follows the edge's meaning. A residual-scan
registration, configuration, verifier contract, or residual predicate change
invalidates the applicable `registered-residual-content` evidence and its
dependent dispositions; a predicate-owner change invalidates receipts whose
acceptance predicate it owns. Re-establishing `profile-load` proves authority
and resolvability only. It never refreshes the downstream content or judgment
receipt automatically.

Queue receipts bind bytes/revisions. A structural or fingerprint change invalidates structure, readiness, and completion receipts; `state_revision` changes invalidate lifecycle/hold predicates. A Terminal Proof pass binds exact Coverage, Progress, Queue, and Proof bytes, so any byte change invalidates it. The controlled `completion-candidate -> complete` transition may consume that pass once and records Progress before/after fingerprints; reuse on the new bytes requires a new pass. Other reuse requires the same canonical paths, revisions, fingerprints, mode, and checker.

Corpus Planning receipts are direct byte-bound evidence. A change to the
selected Profile manifest, Profile Scope, Corpus Planning slot, Global Map, Capability
Matrix, Gap Register, any canonical state fingerprint or Queue revision, or
the repository snapshot invalidates the pass. Its applicability to batch close
is recomputed from R13 selection and the exact validator-parsed affected-path
set; an old receipt cannot be reused merely because the three artifact paths
still have the same names.

### Systemic Expansion

If a targeted check finds a systemic problem that may affect pages of the same kind:

1. Record the failure signature and the suspected family;
2. Move that family's receipts for the corresponding dimension into `suspect`;
3. Expand to a bounded sample;
4. If it recurs, invalidate the whole family and create a repair batch;
5. After the fix, re-run only the invalidated dimensions and their necessary global invariants.

A local problem MUST NOT lead to unbounded re-review of the whole vault, and a passing sample MUST NOT override a known failure.

## Specialized Audit Boundary

A specialized Audit MUST first declare its cross-batch invariant:

| Audit | Primary global question | Reuse boundary |
|---|---|---|
| Source Audit | Whether identity/currentness, claim conflicts, promotion, and affected-note propagation are consistent | Does not rewrite general mechanisms of unchanged pages |
| Case Audit | Whether public fact, inference, recommendation, metric provenance, and transferability are consistent across cases | Reuses passed canonical mechanisms |
| Profile-registered Specialized Audit | Whether the cross-batch invariants registered in the `Routing And Gate Registry` are intact | Reuses canonical content review unrelated to that invariant |
| Metadata Migration Audit | Whether the schema migration conserves content and statuses have evidence | Does not treat migration as authoring review |
| Full-scope Reconciliation | Whether owner, scope, coverage, queue, and graph are closed | Does not replace the Terminal Proof |

If a specialized Audit finds a local receipt already invalidated, it SHOULD create an explicit repair item; it MUST NOT silently rewrite a page in the specialized report and then keep relying on the old Batch Review.

## Receipt Sealing and the Cold Chain

Receipt registers are append-only records, but append-only is a property of records, not of parse cost. An adopter whose shared close register grew past sixty megabytes found every later state transition re-deserializing all of it — the audit trail's own weight priced the runtime out of its execution channel. Sealing is the structural answer: it moves rows that are already verified frozen history out of the hot parse path while keeping every byte and every receipt ID resolvable forever. Sealing is never deletion, redaction, or a second chance at validation.

Sealed evidence MUST live inside the repository it is evidence for: a consistency run MUST refuse a cold path any component of which is a symlink, and a cold file carrying a second hard link, because a symlinked intermediate directory moves the whole archive outside the repository snapshot while every per-file check still passes, and a second name for sealed bytes is a second writer for them. These are containment checks evaluated once per run against an ordinary mistake or a stale working copy; they are not a defence against a party who can change the filesystem between the check and its use, and nothing may claim they are.

`Tools/seal_receipts.py` is the one sealing writer. The cold namespace is `.cambium/receipts/cold/`: sealed segments under `segments/` carry the moved rows verbatim, born-cold close evidence lives under `close-evidence/` (see [[kernel/K12 Quality Assurance/09 Batch-close Closed List|K12/09]]), and three append-only registers make the cold side resolvable and recoverable — `manifest.jsonl`, one entry per segment binding its exact bytes (`segment_sha256`, `segment_bytes`), record count, source register, and seal identity (task, state revision, seal time); `index.jsonl`, one thin projection per sealed receipt (identity and era fields plus the record's own byte hash and its segment position); and `journal.jsonl`, one `begin` and one `complete` row per seal transaction. Every row of all three names the seal receipt that wrote it. The hot receipt catalog never deserializes the cold namespace.

Sealing is a verified checkpoint. The tool MUST refuse to seal unless the complete runtime validation — the one that revalidates every closed batch's frozen bundle field by field — passes with zero errors at seal time, no writer lock is active, and no Coverage delta application is pending.

**What sealing retires is deserialization, not integrity.** Every consistency run MUST re-hash every sealed segment against its manifest entry, MUST prove every index projection against the exact sealed line it names, and MUST prove both cold registers against the seal receipt that wrote them — which records the byte hash of the manifest rows and of the index rows one transaction appended, and which is itself never sealed, so the cold chain terminates in the hot receipt register where every other claim in this runtime terminates. Rows attributed to a seal whose binding does not hold are not evidence and MUST NOT resolve for any consumer, in the same run that reports them. A projection nothing checks is an assertion, and presence with an exact byte size is not content: a same-length edit to a sealed verdict passes a size check silently.

This obligation is not traded away for speed, and the trade was never real. Measured on a sixty-five megabyte adopter archive: re-hashing every segment and every projected record costs 0.42s per run, while re-deserializing the same records to rebuild their projections costs a further 1.33s. The second number is what sealing buys out; the first is what integrity costs, and it is paid every run.

What does drop is the *body-level* obligation for sealed rows, because the full revalidation ran clean against exactly the bytes still on disk. Given the byte and binding proofs above, a consistency run reads a closed batch's sealed evidence trio — batch-close gate, pre-close Queue consistency snapshot, and Coverage delta application, which seal together or not at all — through the projections, checking that they still carry the identities their producers recorded and are still bound by the hot close transition. A missing segment, a size or hash drift, a projection that no longer names its own record, a segment no manifest row names, an unfinished seal transaction, or a sealed ID that still has a hot twin fails the run closed.

Sealing is the one operation that REMOVES bytes from a register, and that is why **sealing is a maintenance-window operation, not a concurrent one**. An adopter MUST run it only in a declared quiet window, and MUST confirm beforehand that no other writer, checker, or receipt appender is running against the repository. This standard does not define a concurrent sealing protocol, and an implementation MUST NOT present one.

Within that boundary the runtime still guards the accident. Every managed receipt append and every seal takes the same exclusive marker (`.cambium/tmp/receipt-append.free` renamed to `.held` and back — a rename, because a lock that cannot be released on a mount that refuses `unlink` is not a lock), with lock order always the runtime writer lock and then this marker. The reason is worth stating exactly: comparing hashes on either side of the rewrite window narrows that window and cannot close it, so a receipt appended inside it is dropped, and dropped invisibly, because the post-seal validation reads the evidence set the row is now missing from. The marker makes that mistake fail rather than corrupt. It is NOT a proof of mutual exclusion under arbitrary concurrency — it is re-entrant per process, binds only appenders that use the shared primitive, and does not defend its own marker paths — and no page, tool, or receipt may claim otherwise. Behind it the rewrite still MUST carry across any tail it did not plan for: a seal may remove only the rows it sealed.

Sealing MUST also be a compare-and-swap over every byte the plan was computed from — the three canonical state files and every file under `.cambium/receipts`, hot and cold — re-compared inside the locks before the first write.

Publication MUST be journalled: the `begin` row and a hash-bound pending record land before the first segment byte, and the `complete` row lands only after every postcondition of the transaction has been re-proved. A writer that dies mid-transaction therefore leaves a state that fails every later run closed.

Automatic recovery is scoped, and the scope is normative. `seal_receipts.py --reconcile --apply` MUST deterministically finish the publication paths the sealing writer itself implements. Every other interruption is required only to **fail closed, preserve recoverable evidence, and be resolvable by a documented operator runbook** — this standard does not require byte-level automatic convergence from every possible crash point, and an implementation MUST NOT claim it. Recovery MUST NOT take a lock from a writer that is still running, and MUST NOT act on a pending record whose bytes no longer match the hash the journal bound to it — a recovery plan that has been edited since the transaction wrote it is not a recovery plan.

An archive is exactly as trustworthy as the writer that produced it, so the seal receipt's producer and version MUST be a currently supported sealing protocol. A version that did not exclude concurrent appenders, or did not bind its registers to a receipt, cannot be certified after the fact.

A sealed receipt satisfies existence and identity consumers through its projection. A consumer that requires live field revalidation of a sealed body and has no explicit sealed branch MUST fail closed rather than pass silently — sealing recorded that exactly that revalidation already ran clean, and a consumer that cannot know this must say so rather than guess. Rows the current sealing protocol never moves: the global transition history, Standards adoption records, contract and operational amendments, the seal register itself, activation and confirmation gates, batch-review wrappers still referenced by their items, the aggregate a recorded Queue transition consumed to discharge a Standards revalidation, any receipt bound to a batch that is not terminally closed, and every receipt currently named by `Coverage.pages[].property_state.*.evidence_receipt`. A current page-review owner also keeps its reviewer attestation hot. If a current property points at the Delta member of a closed bundle, the trio and every child body needed by its hot producer-era replay remain hot as one reachable closure; only a later owner transition that replaces the property pointer makes that old bundle sealable.

Silent non-resolution is the third option and it is not available: a reference that resolves in neither namespace MUST fail the run closed, and MUST NOT be read as the absence of what it asserts. The failure this is written from sealed the revalidation aggregates closed batches' transitions had consumed — transitions stayed hot, what they bind went cold, the replay resolved nothing, and discharged obligations silently reopened on batches the `standards-revalidation` Gate's own K00/12 lifecycle cells then refuse, so nothing could discharge them again. The archive was intact and the run reported zero errors; what was lost was resolvability.

An explicit sealed branch MAY resolve a sealed body rather than only its projection, and MUST re-prove that record's own `record_sha256` at the read — a branch reading a body it has not just re-proved is reading the index's claim about the record, not the record. It resolves only what a consumer asks for; one that walked the archive would give back what sealing bought. Body resolution MUST NOT be presented as a substitute for keeping live-referenced rows hot: it repairs an archive already sealed against this rule, while the never-moves list is what stops the next seal from needing the repair.

## Terminal Reconciliation Rules

The canonical Terminal Audit procedure lives in [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]], while the Terminal Proof field list (including `full_deterministic_results`) lives in [[kernel/K12 Quality Assurance/16 Terminal Proof Contract#Terminal Proof Contract|Terminal Proof Contract]], which also states the `unresolved_invalidations` threshold this section's reconciliation feeds; this section specifies only the evidence reuse and invalidation reconciliation rules within that procedure.

Reusing a receipt is not lowering the standard; it requires proving that the audited object and the acceptance conditions have not undergone relevant change.

## Related

- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]]
- [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]]
- [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
