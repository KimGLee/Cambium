## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]].
- Next: [[kernel/00 Standards Control/06 Completion Precedence and Task Contract|Completion Precedence and Task Contract]].

## Core Principles

1. One canonical source: a concept is maintained in full in exactly one canonical note.
2. Separation of concerns: knowledge, terminology, system design, cases, and expression artifacts each carry distinct responsibilities.
3. Depth over volume: the standard is whether a question is explained thoroughly, not file count or word count.
4. Explain the why: explain not only what it is, but also why it exists, why it is designed this way, and why the naive approach fails.
5. Reusable knowledge: shared definitions are reused via wiki links, not copied across pages.
6. Local readability: after referencing an external term, the current paragraph SHOULD still be understandable on its own.
7. Evidence first: key facts, formulas, protocols, and time-sensitive content MUST have reliable sources.
8. Foundations remain complete: the application focus of the selected `Profile Scope` does not mean its foundational knowledge may be deleted or compressed.
9. Source-to-knowledge: external sources first pass through claim extraction, synthesis, and ownership determination before changing canonical knowledge.
10. Expression separation: derived expression material is registered by the `Expression Layer Entry` and stored independently of canonical knowledge.
11. No empty completion: empty-shell pages, placeholder links, and core pages of only two or three sentences do not count as complete.
12. Continuous verification: every content batch runs link, formula, rendering, source, duplication, and coverage checks.
13. State separation: task, authoring, expression, evidence, and learning states MUST NOT substitute for one another.
14. Durable coverage: every in-scope page and Required knowledge object has a Coverage Ledger disposition.
15. Time is not proof: earliest run time, checkpoints, and hard stops cannot replace the Completion Gate.
16. Deterministic-first rendering: check source files in full, with static compile / parse triggered by content; UI, screenshots, and visual models are used only when deterministic evidence cannot eliminate a specific display uncertainty; screen recording is used only for timing or interaction issues that static evidence cannot express.
17. Guidance is durable: mid-task user guidance enters the Amendment Log and MUST NOT be kept only in ephemeral conversation context.
18. Authority is not evidence: the user decides what the current task does; whether a technical claim holds is still decided by sources and verification.
19. Incremental amendment: new guidance modifies only the contract dimensions it explicitly touches; non-conflicting constraints remain in effect.
20. Modular ownership: every rule has a canonical owner in one leaf module; domain MOCs handle routing only.
21. Deterministic loading: the modules to read are resolved via Read Sets, triggers, and gates; no ad-hoc guessing, and no requirement to read an entire domain in full.
22. Content conservation: Standards splits and migrations MUST use block-by-block mapping; without separate authorization, rules MUST NOT be trimmed, summarized, or deleted under cover of structural adjustment.
23. Language contract: reader-facing language, canonical identity, display order, and exception boundaries are registered by the selected `Language Contract`; the kernel does not hard-code a specific language.

## Standards Map

- `Read Sets` [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]: combines the leaf modules to read by task, event, and execution phase.
- `01` [[kernel/01 Scope and Architecture Standard|Scope and Architecture Standard]]: generic scope boundaries, foundation preservation, logical architecture, and the concrete scope binding provided by `Profile Scope`.
- `02` [[kernel/02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]: long-running task contract, Mid-task Guidance, time semantics, task state, Coverage Ledger, batch, resume, and Terminal Proof.
- `03` [[kernel/03 Note Types and Ownership Standard|Note Types and Ownership Standard]]: note types, Process / Flow, canonical ownership, split, and duplication.
- `04` [[kernel/04 Content Depth Standard|Content Depth Standard]]: Atomic / Core / System depth, Process / Flow, system chains, and evaluation provenance.
- `05` [[kernel/05 Terminology Standard|Terminology Standard]]: proper-noun extraction, aliases, reuse, and emerging terminology.
- `06` [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: user hypotheses / source leads, the source-to-knowledge pipeline, synthesis, graph impact, and promotion.
- `07` [[kernel/07 Sources and Accuracy Standard|Sources and Accuracy Standard]]: source roles, claims, formulas, metrics, and freshness verification.
- `08` [[kernel/08 Metadata and Status Standard|Metadata and Status Standard]]: type, domain, priority, authoring / expression / learning status, coverage disposition, and evidence maturity.
- `09` [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]: body links, structural navigation, path, alias, and verification.
- `10` [[kernel/10 Writing and Formatting Standard|Writing and Formatting Standard]]: naming, formulas, tables, diagrams, rendering workflow, and the reader-facing language binding provided by `Language Contract`.
- `11` [[kernel/11 Expression Layer Standard|Expression Layer Standard]]: expression artifacts, coverage, readiness, evidence binding, and migration audit; the concrete implementation is registered by the `Expression Layer Entry`.
- `12` [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]]: single-note, batch, Guidance / Coverage reconciliation, module, source promotion, tiered rendering, and Terminal Audit; extension QA dimensions, scans, and gates are activated by the `Audit Dimension Registry`, the `Registered Scan Registry`, and the `Routing And Gate Registry` respectively.

## Cross-domain Rule Registry

The following high-risk objects have a single canonical owner corpus-wide. Modifying these objects means modifying only the owner file; every other location MAY reference them only via Wiki Link or a registered slot, and MUST NOT copy the content (whether or not slightly rephrased).

| Object | Canonical owner |
|---|---|
| Terminal Proof formula | [[kernel/02 Build Execution/07 Completion and Handoff|Completion and Handoff]] |
| Terminal Audit procedure and Proof field list | [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]] |
| `task_state` vocabulary | [[kernel/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]] |
| authoring / expression / learning status vocabularies | [[kernel/08 Metadata and Status/03 Status Axes|Status Axes]] + `Expression Status Axis` role |
| `evidence_maturity` definition | [[kernel/08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]] |
| Evidence roles | [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Source Note / Research Synthesis templates | [[kernel/06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]] |
| Evaluation provenance element list | [[kernel/07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]] |
| Official source policy | [[kernel/07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]] |
| Reader-facing language policy | `Language Contract` slot |
| Expression-layer language policy | `Language Contract` slot + `Expression Layer Entry` registry |
| Deep-dive expression skeleton | `Expression Layer Entry` registry |
| Batch / Coverage acceptance checklist | [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]] |
| Source-to-Knowledge pipeline | [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Freshness and volatility vocabulary | [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] |
| Retirement and merge procedure | [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]] |
| Maintenance-run budget envelope | [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]] |

## Control Registry

The Cross-domain Rule Registry governs content rules — "where the rule lives"; this Control Registry governs control obligations — "where the check happens". Each risk object has one and only one canonical gate; other layers only verify that a receipt exists and has not been invalidated, and do not re-check.

| Risk object | Canonical gate (sole) | Behavior of other layers |
|---|---|---|
| Wiki link integrity | Batch close: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Closed List]] check_links produces the receipt | Note close: only this page's `--scope` self-check; migration/retirement: targeted retargeting only; the Terminal Audit verifies the last batch's receipt and does not re-run |
| Frontmatter vocabulary | Batch close: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Closed List]] item 7 check_vocab produces the receipt | Note close: `--scope` self-check; the Terminal Audit trusts the receipt |
| Concurrent write conflicts | At batch activation: the integrator runs the manifest intersection check per Coverage `next_batch` ([[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches) | Concurrent batches write only their own manifest pages, receipts directory, and delta files; global state files are integrator-exclusive |
| Content correctness (manual) | Note close: [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review|12/01]] review by tier | Batch-level manual review scope = changed ∪ invalidated ∪ sampled; long-term P0 assurance is carried by freshness re-review; the Terminal Audit verifies receipts + bounded sampling |
| Coverage reconciliation | Batch close: file-count only (Closed List item 4); the issue list runs per [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|12/03]] before module completion and completion-candidate | Once after inventory and once on scope/guidance changes; no reconciliation at batch start; before completion-candidate it merges with Terminal Audit step 4 |
| Standards version consistency | Automatic version self-check at batch activation: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Active-task Adoption|Active-task Adoption]] | With a delta, incremental adoption; with no delta, a one-line receipt; the Terminal Audit validates via check_proof |
| Guidance disposition | One full disposition at intake: [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment|02/02]] (threshold: significant Guidance) | Batch close reconciles only the increment after `last_reconciled_guidance_id`; the Terminal Audit verifies dispositions read-only from the ledger |
| Receipt validity | AuditPlan once before batch close: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] | At batch start only the Receipt Register is loaded; the Reuse Gate conditions remain |
| Rendering | Note close Level 0/1: [[kernel/12 Quality Assurance/02 Rendering Verification|12/02]] | Batch close: one enumerated check item; the Terminal Audit trusts the receipt |
| Registered residual-content scan | Batch close: [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Batch-close Closed List|Closed List]] item 6 + the `Registered Scan Registry` residual-scan hook | Other layers reference the Closed List and the registered hooks; no separate corpus-wide scan |
| Duplicate detection | Maintenance runs and governance tasks: [[kernel/12 Quality Assurance/05 Automated and Manual Checks|12/05]] duplicate_check | At batch level only the Closed List's basename-level check; paragraph-level scans do not run every batch |
| Knowledge freshness | check_freshness at maintenance-run start: [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|08/05]] | Not in the batch automatic check list |
