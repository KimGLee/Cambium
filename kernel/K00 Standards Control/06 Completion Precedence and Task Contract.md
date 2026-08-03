## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/05 Core Principles|Core Principles]].
- Next: [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]].

## Definition Of Complete

A module counts as complete only when all of the following conditions hold:

- Topic coverage matches the competency matrix, not merely the nouns the user listed first.
- The prerequisite chain between the mainline registered by the selected `Profile Scope` and the shared foundational layer is continuous, and no foundational page has been demoted to an empty shell by architectural adjustment.
- Core concepts reach the required depth, with links to prerequisites, sub-concepts, applications, and failure modes.
- Proper nouns have been canonicalized, with no duplicate definitions.
- Important pages have examples, evaluation methods, engineering considerations, and reliable sources.
- Expression artifacts registered by the selected `Expression Layer Entry` have passed the R05 separation, evidence, status, binding, migration, and acceptance floor and have bidirectional links with canonical knowledge.
- The Overview, progress, reference, and R05 expression mappings, plus any supplemental profile synchronization route, reflect the current module structure and canonical owners.
- Wiki links reach `missing=0`, `ambiguous=0`.
- Markdown, tables, formulas, images, and graph configuration all work correctly.
- Source-driven new knowledge retains claim-level provenance and passes the canonical promotion gate.

A long-running task counts as complete only when all of the following conditions hold:

- The Coverage Ledger has been reconciled against the file system, scope, exclusions, and the competency matrix.
- The Amendment Log covers all guidance within the cutoff, with no unclassified, accepted-but-unmapped, or implemented-but-unverified items.
- All Required authoring gaps are closed, or the user has explicitly changed the disposition.
- There are no unverified batches or leftover modifications.
- No Required audit evidence remains in direct, dependency, overdue, or systemic `unresolved_invalidations`.
- All applicable Single Note, Batch, Module, R05 Expression Layer, supplemental profile, Source Promotion, and Rendering gates have passed.
- `minimum_run_until` has been reached, and `hard_stop_at` has not been violated.
- The Final Handoff has been written, making explicit the optional, deferred, and external evidence backlog.
- The Terminal Audit has produced the Terminal Proof.

The canonical definition of the machine-checkable formula for task_complete is located in the Completion Policy section of [[kernel/K02 Build Execution/07 Completion and Handoff|Completion and Handoff]].

Authoring completion does not require every frontier conclusion to reach `validated`; but external evidence gaps MUST NOT mask unfinished body text, sources, expression-layer migration, or QA.

## Maintenance Completion

Completion semantics come in two kinds; when the task contract is frozen, one of them MUST be declared, and the two semantics MUST NOT be mixed:

- Build completion: the existing closed-loop semantics, executed per this page's Definition Of Complete; the Terminal Proof applies.
- Maintenance completion: bounded semantics; complete when all of the following conditions hold:
  - The candidate list within this run's budget envelope is closed (the envelope is defined by [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]).
  - The Ledger and `Tools/state/watermark.yaml` have been advanced.
  - Each batch has passed the applicable QA gates.

Maintenance completion does not require a corpus-wide Terminal Proof; deferred items truncated by the budget are digested by the next maintenance run and do not constitute a gap.

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

- Objective, contract version, scope version, queue revision, in-scope domains, and exclusions.
- Standards version and `selected_profile_manifest`, copied exactly from the active Standards state; the selected Rxx route IDs and Runtime Card paths; the actual loaded set (including any namespaced profile route and every Read Set or leaf path actually read back); and gate items not yet triggered. These are frozen by default for content tasks, and a task-level amendment cannot select another profile.
- The target authoring status for P0 / P1 and the selected `Expression Status Axis` values.
- `minimum_run_until`, `checkpoint_at`, `hard_stop_at`.
- The boundaries of Required, optional, deferred, and excluded.
- Whether the current task includes Frontmatter migration, directory migration, or global UI / graph configuration.
- The review window for time-sensitive sources and the external evidence backlog allowed to remain.
- The default acknowledgement, safe switching, and amendment policy for mid-task guidance; the `K02` defaults apply unless otherwise specified.
- The storage location of the Audit Receipt Register, legacy-evidence adoption, and any decision changing the default invalidation/review policy.

Directory, source-to-knowledge, `Language Contract`, `Expression Layer Entry`, and `Profile Scope` defaults already declared by the selected profile manifest and not overridden by the current task are not re-discussed; only items that change the defaults enter this section's decision list.

## Related

- [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[kernel/K02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]
