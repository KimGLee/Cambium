## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/05 Core Principles|Core Principles]].
- Next: [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]].

## Definition Of Complete

A module counts as complete only when all of the following conditions hold:

- When Corpus Planning uses `applicability.state: configured`, topic coverage matches the bound [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract#Capability Matrix Contract|Capability Matrix]], not merely the nouns the user listed first; when it uses `not-applicable`, the recorded reason remains valid for the bounded task scope.
- The prerequisite chain between the mainline registered by the selected `Profile Scope` and the shared foundational layer is continuous, and no foundational page has been demoted to an empty shell by architectural adjustment.
- Core concepts reach the required depth, with links to prerequisites, sub-concepts, applications, and failure modes.
- Proper nouns have been canonicalized, with no duplicate definitions.
- Important pages have examples, evaluation methods, engineering considerations, and reliable sources.
- Expression artifacts registered by the selected `Expression Layer Entry` have passed the R05 separation, evidence, status, binding, migration, and acceptance floor and have bidirectional links with canonical knowledge.
- The Overview, progress, reference, and R05 expression mappings, plus any supplemental profile synchronization route, reflect the current module structure and canonical owners.
- Wiki links reach `missing=0`, `ambiguous=0`.
- Markdown, tables, formulas, images, and graph configuration all work correctly.
- Source-driven new knowledge retains claim-level provenance and passes the canonical promotion gate.

A long-running build task counts as complete only when all of the following conditions hold:

- The Coverage Ledger has been reconciled against the file system, scope, exclusions, and, when Corpus Planning uses `applicability.state: configured`, the bound [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract#Capability Matrix Contract|Capability Matrix]].
- The current Required Queue passes `check_queue.py --require-complete`, its receipt matches the frozen path, structural/state revisions, and fingerprint, and `remaining_required_work_units = 0`.
- The Amendment Log covers all guidance within the cutoff, with no unclassified, accepted-but-unmapped, or implemented-but-unverified items.
- All Required authoring gaps are closed, or the user has explicitly changed the disposition.
- There are no unverified batches or leftover modifications.
- No Required audit evidence remains in direct, dependency, overdue, or systemic `unresolved_invalidations`.
- All applicable Single Note, Batch, Module, R05 Expression Layer, supplemental profile, Source Promotion, and Rendering gates have passed.
- `minimum_run_until` has been reached, and `hard_stop_at` has not been violated.
- The Final Handoff has been written, making explicit the optional, deferred, and external evidence backlog.
- The Terminal Audit has produced the Terminal Proof.

The canonical definition of the machine-checkable formula for build completion is located in the Completion Policy section of [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]].

Authoring completion does not require every frontier conclusion to reach `validated`; but external evidence gaps MUST NOT mask unfinished body text, sources, expression-layer migration, or QA.

## Maintenance Completion

The frozen Task Contract MUST select exactly one completion semantics:

- Build: this page's Definition Of Complete, `completion-candidate`, and Terminal Proof.
- Maintenance: bounded, never `completion-candidate`, and complete only when:
  - The run's [[kernel/K00 Standards Control/08 Maintenance Run Envelope|budget-envelope]] candidate manifest is closed.
  - The Ledger and `Tools/state/watermark.yaml` have been advanced.
  - Each batch has passed the applicable QA gates.

When maintenance work is persistent, resumable, or multi-batch, K13/12's gate
MUST prove those predicates from current budget-manifest, Coverage-advance,
watermark-advance, and applicable batch/close receipts. Bounded single-note
maintenance does not initialize empty `.cambium/` state for that gate.

Maintenance has no corpus-wide Terminal Proof. Budget-truncated items hand off
to the next run and are not a current gap.

## Standard Precedence

When rules conflict, resolve by the following precedence:

```text
User's latest explicit instruction
 -> Knowledge ownership and factual correctness
 -> Safety and data integrity
 -> These knowledge base standards
 -> Existing local style
```

`User's latest explicit instruction` uses incremental amendment semantics: it overrides only conflicting old requirements in the same dimension, and does not automatically delete other scope, acceptance, safety, quality, or time constraints. The user has authority over the current task's goals and priorities; technical judgments raised by the user still require verification per Sources and evidence maturity.

## Task Contract Decisions

Each ultra-long task only needs to confirm the items that change the defaults:

- Objective, contract version, scope version, in-scope domains, exclusions, and exactly one frozen `completion_semantics` value (`build` or `maintenance`); when Required Queue state applies, its path, `queue_revision`, `queue_state_revision`, SHA-256 fingerprint, and current check receipt.
- Standards version and `selected_profile_manifest`, copied exactly from the active Standards state; the selected Rxx route IDs and Runtime Card paths; the actual loaded set (including any namespaced profile route and every Read Set or leaf path actually read back); and gate items not yet triggered. These are frozen by default for content tasks, and a task-level amendment cannot select another profile.
- The target authoring status for P0 / P1 and the selected `Expression Status Axis` values.
- `minimum_run_until`, `checkpoint_at`, `hard_stop_at`.
- The boundaries of Required, optional, deferred, and excluded.
- Whether the current task includes Frontmatter migration, directory migration, or global UI / graph configuration.
- The review window for time-sensitive sources and the external evidence backlog allowed to remain.
- The default acknowledgement, safe switching, and amendment policy for mid-task guidance; the `K13` defaults apply unless otherwise specified.
- The storage location of the Audit Receipt Register, invalidated-evidence adoption, and any decision changing the default invalidation/review policy.

Directory, source-to-knowledge, `Language Contract`, `Expression Layer Entry`, and `Profile Scope` defaults already declared by the selected profile manifest and not overridden by the current task are not re-discussed; only items that change the defaults enter this section's decision list.

## Related

- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction Standard]]
- [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control Standard]]
