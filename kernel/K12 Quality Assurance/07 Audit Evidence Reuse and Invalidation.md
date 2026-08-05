## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]].
- Next: [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]].

## Purpose

This module specifies how verification evidence is reused across single pages, batches, modules, specialized audits, and the Terminal Audit, with protocol rules that prevent later modifications from silently inheriting old results inside the declared trust boundary. The goal is not to reduce quality dimensions but to eliminate two errors:

1. Every layer repeating expensive manual review from scratch, wasting execution time and context;
2. Continuing to rely on an old conclusion after content, dependencies, or rules have changed, merely because a page once passed.

The core chain: changed objects and acceptance predicates generate a dimension-specific AuditPlan, which produces append-only AuditReceipt records carrying dependency / contract fingerprints; receipts are reusable while predicates and fingerprints remain valid, relevant changes trigger invalidation, bounded expansion applies when local failures show systemic impact, and finally Terminal reconciliation runs on the frozen snapshot. Append-only and immutable mean protocol-level history preservation, not cryptographic tamper resistance.

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

Queue receipts bind bytes/revisions. A structural or fingerprint change invalidates structure, readiness, and completion receipts; `state_revision` changes invalidate lifecycle/hold predicates. A Terminal Proof pass binds exact Coverage, Progress, Queue, and Proof bytes, so any byte change invalidates it. The controlled `completion-candidate -> complete` transition may consume that pass once and records Progress before/after fingerprints; reuse on the new bytes requires a new pass. Other reuse requires the same canonical paths, revisions, fingerprints, mode, and checker.

### Systemic Expansion

If a targeted check finds a systemic problem that may affect pages of the same kind:

1. Record the failure signature and the suspected family;
2. Move that family's receipts for the corresponding dimension into `suspect`;
3. Expand to a bounded sample;
4. If it recurs, invalidate the whole family and create a repair batch;
5. After the fix, re-run only the invalidated dimensions and their necessary global invariants.

A local problem MUST NOT lead to unbounded re-review of the whole vault, and a passing sample MUST NOT override a known failure.

## Incremental Audit Planning

Each batch generates an `AuditPlan` exactly once, before close; at batch start only the Audit Receipt Register is loaded, with no separate AuditPlan:

```text
1. Freeze current artifact and contract snapshot.
2. Diff against the latest accepted snapshot.
3. Resolve direct and dependency invalidations.
4. Partition checks into:
   - mandatory full deterministic
   - changed-scope deterministic
   - invalidated semantic review
   - overdue (freshness) targeted review
   - bounded sampling
   - reusable evidence
5. Run checks and emit new receipts.
6. Reconcile invalidated, replaced and reused receipts.
7. Close only when required invalidations are zero.
```

The mandatory full deterministic partition of step 4 is the [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List|Batch-close Closed List]]; this module decides the plan, not the list's membership.

## Incremental By Default

The following checks cover only the changed, invalidated, overdue, or sampled scope by default (long-term assurance for P0/P1 pages is carried by freshness-expiry re-verification, with no permanent manual review scope):

- Manual review of mechanisms, why-chains, failures, and production depth;
- Item-by-item verification of source claims against body tone;
- Deep review of formula derivations and numeric context;
- host-specific rendering exceptions;
- profile-specific semantic review registered in the `Audit Dimension Registry`.

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

## Terminal Reconciliation Rules

The canonical Terminal Audit procedure lives in [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]], while the Terminal Proof field list (including `full_deterministic_results`) lives in [[kernel/K12 Quality Assurance/16 Terminal Proof Contract#Terminal Proof Contract|Terminal Proof Contract]]; this section specifies only the evidence reuse and invalidation reconciliation rules within that procedure.

`unresolved_invalidations` MUST be `0`. Reusing a receipt is not lowering the standard; it requires proving that the audited object and the acceptance conditions have not undergone relevant change.

## Related

- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]]
- [[kernel/K12 Quality Assurance/10 Standards Version Adoption|Standards Version Adoption]]
- [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]]
- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
- [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]]
