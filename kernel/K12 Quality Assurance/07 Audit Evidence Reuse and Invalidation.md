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

Audit evidence is stored per dimension; recording only a vague
`reviewed: true` is not allowed. The sole machine authority for the base
receipt-dimension namespace is
[`audit-dimension-base.yaml`](audit-dimension-base.yaml). These dimensions
separate structural, substantive, numeric, source/currentness,
coverage/integration, rendering, and governance-contract evidence so that a
pass in one concern cannot silently discharge another.

The `Audit Dimension Registry` MAY append profile-owned dimensions, but MUST
NOT delete, rename, or redefine a base dimension from that registry. Its
append unit is a judgment item, not a dimension name, and the declarations it
MUST carry are fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Profile Registration|K12/08]].

Which dimension a kernel judgment item files its verdict under, and whether it emits a receipt at all, is fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map#Item Map|K12/08]]; an item that consumes evidence produced elsewhere does not open a second receipt for the same audit object.

One verification produces one append-only `AuditReceipt` protocol record. The
registered AuditReceipt machine contract is the sole normative source for its
closed fields, shapes, result values, and serialization. This page owns these
field meanings and evidence boundaries:

- `scope`: the pages, module, batch, or vault-wide snapshot the receipt actually covers.
- `acceptance_predicate`: the specific condition evaluated against the recorded scope and bytes; writing only `QA passed` is not allowed.
- `artifact_fingerprint`: covers body content, file path, and the frontmatter fields `type`, `priority`, `tier`, `coverage_disposition`, `lifecycle`, `prerequisites`. **Explicitly excluded**: `authoring_status`, `learning_status`, the readiness statuses registered by the selected `Vocabulary Extensions`, and `last_reviewed`, `last_verified`, `review_by`, `next_batch` — write-backs of status axes and scheduling fields **do not invalidate the receipt**.
- `dependency_fingerprint`: the canonical owners, sources, schemas, MOC, or configuration this dimension depends on.
- `contract_fingerprint`: the relevant control state such as scope, acceptance, exclusions, and queue/guidance cutoff.
- `verifier` / `method`: the declared producer label and version of the script, compiler, manual rubric, or model review; these fields do not authenticate an actor.
- `evidence_ref`: the location of the command result, review record, compiled artifact, or Batch Review evidence.
- `review_due`: when time-sensitive facts need re-verification; stable mechanisms MAY leave it empty.

`last_reviewed`, `last_verified`, file length, or `authoring_status` cannot substitute for an AuditReceipt.

Deterministic and manual producers emit the same registered receipt contract.
A producer-level receipt is a lightweight evidence record; when it enters the
Audit Receipt Register, the AuditPlan layer binds the complete AuditReceipt
identity and uses the producer receipt as its evidence reference.

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
a predicate-owner path or heading, or the `profile-load` contract invalidates
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

Receipt sealing moves verified frozen history out of the hot parse path without
deleting, redacting, reinterpreting, or renaming any receipt identity. The
registered receipt-sealing capability owns storage namespaces, segment and
index schemas, concurrency controls, publication order, and recovery procedure.

Kernel requires these externally observable invariants:

- sealing begins only from a fully valid, current checkpoint and must not race
  another runtime writer;
- every sealed byte remains contained, immutable, hash-bound to its seal
  evidence, and resolvable by the original receipt identity;
- hot and sealed namespaces cannot contain competing copies of one identity;
- evidence still referenced by live state or an undischarged obligation
  remains resolvable with the fields its consumer requires;
- missing, ambiguous, modified, unsupported, or incompletely published sealed
  evidence fails closed in the same run that detects it;
- interruption preserves recoverable evidence and cannot be mistaken for a
  completed seal.

Sealing retires repeated body deserialization, not integrity verification. A
projection may satisfy only consumers whose declared contract needs that
projection; a consumer requiring body fields must resolve and re-prove the
body or fail closed. The Tool implementation and operator runbook determine
how these results are achieved.

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
