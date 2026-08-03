## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]].
- Next: [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]].

## Task Routing Table

All tasks first select R01 Core Bootstrap, then combine the Rxx route for the actual work and any event modules shown below. The Card is loaded first; its paired Read Set is read back when the Card-first protocol requires source text.

| Task | Required Read Set Or Module | Main Decision |
|---|---|---|
| Create a concept page or extend one in a targeted way | [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Single Note Authoring]] | note type, owner, depth, sources, links, and the note gate |
| Create a process page, system page, or complete module | [[kernel/Read Sets/R03 Module Build Read Set\|Module Build]] | logical placement, foundation, dependency order, MOC, and the module gate |
| Extend knowledge from official vendor material, papers, code, cases, or community signals | [[kernel/Read Sets/R04 Source-driven Expansion Read Set\|Source-driven Expansion]], combined with the authoring Read Set | claim, evidence role, gap, promotion, update / new / defer / supersede |
| Build an industry Case Study | [[kernel/Read Sets/R04 Source-driven Expansion Read Set\|Source-driven Expansion]] + [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Single Note Authoring]] | reported fact, inference, recommendation, and metric provenance |
| Create, migrate, or review expression-layer content | [[kernel/Read Sets/R05 Expression Layer Read Set\|R05 Expression Layer]], plus the selected profile's `Expression Layer Entry` and supplemental gates | knowledge vs. expression separation, evidence, readiness, bidirectional binding, and migration coverage |
| Bulk rename, move, split, merge, or directory restructuring | [[kernel/Read Sets/R06 Migration and Refactor Read Set\|Migration and Refactor]] | source / target map, incoming links, ownership, rollback, and content conservation |
| Admit large-scale creation, moves, or deletion to execution | [[kernel/Read Sets/R11 Large-scale Work Admission Read Set\|Large-scale Work Admission]], combined with the route for the actual work | contract, scope, queue, ledger, dependencies, batch acceptance, and evidence readiness |
| Start, resume, pause, or complete a long-running task | [[kernel/Read Sets/R07 Long-running Execution Read Set\|Long-running Execution]], combined with the actual content Read Set | task state, time semantics, Coverage Ledger, Required Queue, and Terminal Proof |
| Run a targeted or specialized audit | [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set\|Targeted and Specialized Audit]], plus the Read Sets related to the finding under review | changed / invalidated / overdue / sampled scope, specialized invariants, and bounded systemic expansion |
| Enter task completion acceptance or Terminal Audit | [[kernel/Read Sets/R08 Audit and Completion Read Set\|Audit and Completion]], plus every route relevant to the completion predicates | frozen snapshot, prerequisite gates, receipt reconciliation, Terminal Proof, and terminal state |
| Modify Standards, Read Sets, or control-plane structure | [[kernel/Read Sets/R09 Standards Governance Read Set\|Standards Governance]] | authority, version, migration map, active task impact, and corpus-wide validation |
| Handle mid-task user guidance, scope, or priority changes | [[kernel/K02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]]; when a hypothesis is involved, additionally load [[kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads\|User Guidance Hypotheses and Source Leads]] | guidance type, authority, evidence role, disposition, safe switching, and version impact |
| Split out a proper-noun term | [[kernel/K05 Terminology/01 Terminology Extraction\|Terminology Extraction]] + [[kernel/K05 Terminology/02 Ownership and Term Structure\|Ownership and Term Structure]] | whether it is reusable, whether a canonical owner already exists, and whether it merits a standalone page |
| Math, formula, table, image, or rendering fixes | Triggered modules of [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Single Note Authoring]] + [[kernel/K12 Quality Assurance/02 Rendering Verification\|Rendering Verification]] | Level 0 / Level 1 deterministic verification; only unresolved display issues escalate to visual recognition |
| Periodic knowledge-corpus update / freshness (Maintenance Run) | [[kernel/Read Sets/R10 Maintenance Run Read Set\|Maintenance Run]] | budget envelope, candidate list, watermark advancement, and bounded completion semantics |

## Pre-execution Gate

Large-scale creation, moves, or deletion selects R11 Large-scale Work Admission and MAY begin only after the following conditions are met:

1. `K00` and Core Bootstrap have been read.
2. Task-specific Read Sets, triggered modules, and gate modules have been resolved per the Task Routing Table.
3. Contract / scope / queue / initial batch / Standards version / selected profile manifest, the loaded set (selected Rxx route IDs and Runtime Card paths, any combined namespaced profile route, and every Read Set or leaf path actually read back), the target scope, the excluded scope, and the latest user requirements have been recorded.
4. `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate have been made explicit; fields not provided are explicitly left empty.
5. The Coverage Ledger has been created or refreshed and reconciled against the file system and exclusions.
6. Ownership, incoming links, user modifications, and the Required Queue have been inventoried.
7. Foundational knowledge dependencies have been identified; all prerequisite content MUST NOT be crammed into the application mainline pages declared by the selected `Profile Scope`.
8. Source-driven tasks have established a source inventory and a claim extraction plan.
9. The current batch's completion conditions, `rendering_mode`, deterministic verification commands, and the objective trigger and unresolved question for any visual escalation have been defined.
10. The latest Audit Receipt Register has been loaded ([[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]]); at start of work only the Register is loaded, no AuditPlan is built — the AuditPlan is built once before batch close.

When any condition is missing, first complete the plan or investigation; do not proceed directly to large-scale creation, moves, or deletion.
