## Navigation

- Parent: [[kernel/K12 Quality Assurance Standard|K12 Quality Assurance Standard]].
- Previous: [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]].
- Next: [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract|Gate Receipt Payload Contract]].

## Terminal Proof Contract

The Terminal Proof is the machine-readable completion claim produced after the [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence#Terminal Audit|Terminal Audit]] for `completion_semantics: build`. It does not apply to maintenance completion.

The registered terminal-proof machine contract is the sole normative source for its fields, shapes, closed values, and serialization. This page owns the meaning and acceptance boundary of those fields. A Terminal Proof must bind:

- one task, scope, Contract, Standards, selected Profile, and frozen loading
  selection;
- the canonical Coverage, Progress, and Required Queue identities, revisions,
  fingerprints, and zero-remaining-work result;
- the guidance cutoff and reconciliation result;
- Coverage reconciliation and zero Required authoring gaps;
- the complete deterministic result set and current Queue, Corpus Planning,
  Profile-load, and Terminal Proof Gate evidence;
- manual review, rendering evidence, AuditReceipt dimension coverage, reuse,
  supersession, invalidation, sampling, and systemic-expansion results;
- unresolved-invalidation and unverified-batch counts;
- the deferred external-evidence backlog, time-contract result, and Final
  Handoff.

The Proof copies the resolved loading selection frozen by the Task Contract; it does not select routes, Cards, Read Sets, or Kernel owners. A live Gate result cannot authorize the Proof to declare a different selection. The selected Profile's dependency closure is a separate `profile-load` result and is not inserted into the task's loaded Kernel set merely because it was validated.

## Evidence Bindings

`full_deterministic_results` references the complete deterministic set run against the final frozen snapshot. `unverified_batches = 0` requires the Queue-derived merge view to be empty; it cannot be satisfied by a separate manually maintained list.

Every build Proof consumes one current `required-queue-completion` receipt and one current `corpus-plan-structure` receipt, including when the selected Profile declares Corpus Planning not applicable. When it is configured, the Proof also consumes one current `corpus-plan-semantic-acceptance` receipt covering every current Capability ID under the Profile-authorized role and decision scope. The Proof binds these terminal Gate records through the canonical Terminal Audit receipt register; the separate AuditReceipt register supplies dimension evidence. Both registers and every cited record must bind the same Profile, planning artifacts, task state, Queue revisions, and frozen repository snapshot as the Proof. Missing, duplicate, rejected, malformed, aliased, or stale evidence blocks completion.

Rendering evidence states the highest level actually used and the verification result. Where no visual exception trigger exists, an explicit not-applicable result is sufficient; absence of UI, screenshots, or recordings does not block completion.

Dimension coverage accounts for every base dimension in K12/07 and every applicable registered extension dimension. A dimension that ran cites the current receipts carrying its verdict; one with no in-scope object carries an explicit reasoned not-applicable decision. Omission, an empty receipt set, an unresolvable registry, duplicate use across dimensions, or a stale or invalidated receipt is not a pass. Whether a not-applicable rationale is true remains a semantic review item.

## Terminal Completion Gate

After the task enters `completion-candidate`, the frozen candidate must produce new current results for `required-queue-completion`, `corpus-plan-structure`, applicable `corpus-plan-semantic-acceptance`, `profile-load`, and `terminal-proof`. The Queue result used to enter `completion-candidate` cannot be reused because the transition changed Progress bytes. Only the registered task-state transaction may consume the `terminal-proof` pass to authorize `complete`.

Terminal validation must use the canonical adopter runtime objects for this task; caller-selected substitutes are forbidden. It verifies one common task, scope, Standards, Profile, Contract, state, Queue, and repository identity; zero pending Guidance and Amendment; zero remaining Required work and Coverage gaps; receipt-chain agreement; and evidence currency at the completion boundary. Structural lint that does not resolve and bind authoritative runtime objects cannot authorize `complete`.

Only Proofs produced under the current hard-cut contract enter Cambium runtime. After completion, those current-format Proofs may be retained as immutable history, but historical preservation never restores current authorization. Objects from retired runtime contracts remain outside Cambium as external archives and are not parsed or replayed.

## Evidence Trust Boundary

Repository-root validation checks Proof and referenced local evidence for structure, declared producer protocol, exact state and snapshot bindings, transition and receipt-chain agreement, and currency. It can reject missing, stale, incomplete, or internally inconsistent evidence.

These checks do not authenticate the executable, operating-system actor, or human/process identity and independence of a reviewer. Hashes are byte-integrity bindings, not signed provenance. Adversarial provenance requires an external trust anchor such as signed receipts or a protected execution service; that facility is outside this baseline.

Only when all open-guidance counters, remaining Required work, Required authoring gaps, unverified batches, and unresolved invalidations are zero, and all applicable Gates pass, may task state become `complete`.
