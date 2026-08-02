## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]].
- Next: [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].

## Task Routing Table

All tasks first load [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]], then combine task-specific Read Sets or event modules per the table below.

| Task | Required Read Set Or Module | Main Decision |
|---|---|---|
| Create a concept page or extend one in a targeted way | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | note type, owner, depth, sources, links, and the note gate |
| Create a process page, system page, or complete module | [[kernel/Read Sets/03 Module Build Read Set\|Module Build]] | logical placement, foundation, dependency order, MOC, and the module gate |
| Extend knowledge from official vendor material, papers, code, cases, or community signals | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]], combined with the authoring Read Set | claim, evidence role, gap, promotion, update / new / defer / supersede |
| Build an industry Case Study | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] + [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | reported fact, inference, recommendation, and metric provenance |
| Create, migrate, or review expression-layer content | The `Expression Layer Read Set` registered in the selected profile's `Routing And Gate Registry` | knowledge vs. expression separation, expression rules, follow-up question structure, and migration coverage |
| Bulk rename, move, split, merge, or directory restructuring | [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] | source / target map, incoming links, ownership, rollback, and content conservation |
| Start, resume, pause, or complete a long-running task | [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]], combined with the actual content Read Set | task state, time semantics, Coverage Ledger, Required Queue, and Terminal Proof |
| Content review, batch close, or completion acceptance | [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]], plus the Read Sets related to the finding under review | correctness, depth, provenance, integration, rendering, and terminal state |
| Modify Standards, Read Sets, or control-plane structure | [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance]] | authority, version, migration map, active task impact, and corpus-wide validation |
| Handle mid-task user guidance, scope, or priority changes | [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]]; when a hypothesis is involved, additionally load [[kernel/06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads\|User Guidance Hypotheses and Source Leads]] | guidance type, authority, evidence role, disposition, safe switching, and version impact |
| Split out a proper-noun term | [[kernel/05 Terminology/01 Terminology Extraction\|Terminology Extraction]] + [[kernel/05 Terminology/02 Ownership and Term Structure\|Ownership and Term Structure]] | whether it is reusable, whether a canonical owner already exists, and whether it merits a standalone page |
| Math, formula, table, image, or rendering fixes | Triggered modules of [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] + [[kernel/12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | Level 0 / Level 1 deterministic verification; only unresolved display issues escalate to visual recognition |
| Periodic knowledge-corpus update / freshness (Maintenance Run) | [[kernel/Read Sets/10 Maintenance Run Read Set\|Maintenance Run]] | budget envelope, candidate list, watermark advancement, and bounded completion semantics |

## Effort Tiering

Page-level acceptance intensity is executed by S/M/L tiering. This section is the canonical owner of the tiering rules; the Tiering tables in the Runtime Cards are compiled from this section.

| Tier | Determination | Ceremony |
|---|---|---|
| S | priority=P2, or terminology stub / placeholder / link-aggregation pages | script checks only; no note gate; spot check at batch close per [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review\|12/03]] |
| M | regular priority=P1 pages | script checks + the corresponding Card's Gate list; the note gate is folded into the batch gate |
| L | priority=P0, or core concept / process-flow / system / risk-control mainline pages, plus the additional L-tier triggers registered in the selected profile's `Routing And Gate Registry` | full procedure: complete [[kernel/12 Quality Assurance/01 Quality Dimensions and Single Note Review\|12/01]] review + a standalone note gate + applicable expression migration checks |

- The specific grant conditions for P0 / P1 are registered by the selected profile's `Priority Rubric`.
- Escalate one tier when tiering is disputed.
- Each page's tier is recorded in the Coverage Ledger's `tier` field (schema: `Tools/schemas/coverage_ledger.template.yaml`).
- Tiering only adjusts the intensity of the acceptance ceremony; it does not change any content quality standard itself.

### Priority Quota

tier is derived from priority; priority inflation defeats tiering. Kernel default corpus-wide quotas:

- `P0` share target ≤15%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- `P1` share target ≤35%; the specific grant targets are registered by the selected profile's `Priority Rubric`.
- All remaining pages are `P2` (including all terminology stubs, placeholder pages, and the vast majority of Source Notes).

P0/P1 pages exceeding quota MUST be demoted, or an explicit exemption rationale MUST be recorded in the Coverage Ledger; over-allocation without an exemption record is handled as a coverage reconciliation gap. Coverage reconciliation for REBASE and Maintenance Runs MUST check the priority and tier distributions (`Tools/check_vocab.py` outputs distribution statistics and over-allocation candidates). The selected profile MAY override the 15% / 35% defaults, but MUST register the override explicitly.

## Maintenance Run Envelope

When a maintenance run starts, a budget envelope MUST be declared, choosing one of three: N pages, N batches, or N hours.

- Candidate list = the `check_freshness` overdue list ∪ the watermark delta ∪ `needs_rereview` marks ∪ the candidates pool (duplicate / vocab / language); sort by priority, then truncate to the budget.
- Candidates arising from changed pages within a batch are adjudicated in that batch (the author is present; lowest cost); candidates from existing pages always enter the pool, and neither block any gate nor surface as to-dos.
- A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only: the record is kept, but it does not count as a to-do, does not appear in gate output, and does not count toward any completion determination; it re-enters the pool when hit again by a new scan.
- At maintenance-run start, output the deferred age distribution; items lingering more than 3 runs MUST be explicitly dispositioned: demotion, retirement, or a recorded retention rationale. "Deferred does not constitute a gap" is retained, but is not a basis for skipping checks.
- For retirement of high-in-degree pages, the incoming-link retargeting work counts against the maintenance-run budget as pages, converted at "retargeted links ÷ 6".
- The truncated portion is recorded as deferred in the Ledger and does not constitute a gap.
- Stopping points are batch boundaries; do not stop mid-batch.

## Pre-execution Gate

Large-scale modification MAY begin only after the following conditions are met:

1. `00` and Core Bootstrap have been read.
2. Task-specific Read Sets, triggered modules, and gate modules have been resolved per the Task Routing Table.
3. Contract / scope / queue / initial batch / Standards version, the loaded set (Runtime Card IDs, artifacts resolved by the `Runtime Card Provider`, and module paths read back on escalation), the target scope, the excluded scope, and the latest user requirements have been recorded.
4. `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate have been made explicit; fields not provided are explicitly left empty.
5. The Coverage Ledger has been created or refreshed and reconciled against the file system and exclusions.
6. Ownership, incoming links, user modifications, and the Required Queue have been inventoried.
7. Foundational knowledge dependencies have been identified; all prerequisite content MUST NOT be crammed into the application mainline pages declared by the selected `Profile Scope`.
8. Source-driven tasks have established a source inventory and a claim extraction plan.
9. The current batch's completion conditions, `rendering_mode`, deterministic verification commands, and the objective trigger and unresolved question for any visual escalation have been defined.
10. The latest Audit Receipt Register has been loaded ([[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]); at start of work only the Register is loaded, no AuditPlan is built — the AuditPlan is built once before batch close.

When any condition is missing, first complete the plan or investigation; do not proceed directly to large-scale creation, moves, or deletion.

## Default Constraints Snapshot

The following rules are in effect by default in all long-running tasks:

- The selected profile's `Profile Scope` registers the content mainline, the foundational knowledge layer, and the completeness predicates; the kernel requires that the mainline and the foundational knowledge be preserved together.
- The excluded scope is read from the selected profile's `Profile Scope` / `Excluded Scope` role; the kernel does not hard-code deployment paths.
- Active Standards are a protected control plane; frozen during content-building tasks, and only a governance change explicitly authorized by the user MAY modify them.
- The reader-facing language values for folders, file names, knowledge body, titles, and first-occurrence terms are provided by the selected profile's `Language Contract`.
- A knowledge object has exactly one canonical owner; other pages reuse it via wiki links.
- Proper-noun definitions, topic mechanisms, system interactions, case applications, and expression-layer content are maintained in separate layers; expression artifacts are registered by the `Expression Layer Entry`.
- External sources MUST NOT be directly equated with canonical knowledge; they MUST pass through the source-to-knowledge pipeline.
- Do not create empty-shell pages, long-lived unresolved links, or P0 / P1 core pages of only two or three sentences.
- Do not roll back, overwrite, or delete existing user modifications whose origin cannot be confirmed.
- Each batch synchronizes body links, metadata, Sources, Expression Layer mapping, and QA; hub pages such as Overview / MOC are synchronized by the integrator after batch merge ([[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]]).
- Batch, targeted audits, and the Terminal Audit reuse still-valid dimension-specific evidence via [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]; old state MUST NOT be trusted blindly, and all manual review MUST NOT be redone indiscriminately.
- `task_state`, `authoring_status`, the profile-owned expression status axis, `evidence_maturity`, and `learning_status` are maintained separately; the specific expression axis is registered by the `Expression Layer Entry`.
- Mid-task Guidance Events MUST be classified, have their disposition recorded, and be mapped to the Amendment Log, Coverage Ledger, Required Queue, or source intake.
- The user has authority over task scope and priority; user hypotheses and source leads still require evidence verification.
- Direct content extraction and structural checks run in full; static compile / parse is triggered by content; the `knowledge-host UI` bound by the selected profile, screenshots, and visual models are used only when deterministic evidence cannot eliminate a specific display uncertainty.
- Screen recording is used only for timing or interaction issues that static evidence and targeted screenshots cannot express.
- Completion MUST satisfy `missing=0`, `ambiguous=0`, Guidance / Coverage Reconciliation, the applicable QA gates, and the Terminal Proof.

## Batch Execution Checklist

1. Version self-check: compare the current version in [[kernel/00 Standards Control/03 Standards Governance|00/03]] with the contract-frozen version; with a delta, adopt incrementally per [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] Active-task Adoption; with no delta, record a one-line receipt. Standards changes are discovered by the batch-activation self-check; user notification serves only as a reminder.
2. Reconcile incremental guidance: reconcile only the Guidance Events after `last_reconciled_guidance_id` against the Amendment Log.
3. Select the next batch from the ordered Required Queue.
4. Resolve note type, canonical owner, and target status.
5. Resolve prerequisite and foundation gaps.
6. Collect and classify sources when needed.
7. Write one complete dependency-aware batch.
8. Integrate body links, navigation, metadata, sources, and Expression Layer mapping.
9. Before batch close, build the AuditPlan once and process receipts ([[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]]): complete the `--scope` self-check, the required incremental manual / rendering QA, and the [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|12/03]] in-batch items; issue or supersede dimension-specific AuditReceipts and write out the delta; the batch enters `merge-ready`. Visual checks escalate only on a recorded exception trigger.
10. The integrator performs the serial merge ([[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches): apply the delta, run the Batch-close Closed List, verify the 12/03 global items, and update the global Ledger and Amendment Log; batches themselves do not write the global ledger.
11. Close the batch only after Batch Review passes and unresolved invalidations = 0; otherwise it stays active or merge-ready.

Note: Coverage reconciliation is not executed at batch start; reconciliation is executed at batch close.
