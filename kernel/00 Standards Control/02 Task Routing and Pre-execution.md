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
