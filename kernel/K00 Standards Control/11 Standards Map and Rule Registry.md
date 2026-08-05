## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]].
- Next: [[kernel/K00 Standards Control/12 Control Registry|Control Registry]].

## Standards Map

- `Cards` [[kernel/Cards/Card Index|Card Index]]: kernel-owned compiled task guidance; every routine task enters here before escalating to Read Sets and leaf owners.
- `Read Sets` [[kernel/Read Sets/Read Sets Index|Read Sets Index]]: combines the leaf modules to read by task, event, and execution phase.
- `K00` [[kernel/K00 Standards Overview|Standards Overview]] and [[kernel/K00 Standards Control/03 Standards Governance|Standards Control]]: entry, route loading, precedence, governance, defaults, and control registries.
- `K01` [[kernel/K01 Scope and Architecture Standard|Scope and Architecture Standard]]: generic scope boundaries, foundation preservation, logical architecture, and the concrete scope binding provided by `Profile Scope`.
- `K02` [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction Standard]]: inventory, Coverage reconciliation, architecture and dependency planning, knowledge-batch production, and migration safety.
- `K03` [[kernel/K03 Note Types and Ownership Standard|Note Types and Ownership Standard]]: note types, Process / Flow, canonical ownership, split, and duplication.
- `K04` [[kernel/K04 Content Depth Standard|Content Depth Standard]]: Atomic / Core / System depth, Process / Flow, system chains, and evaluation provenance.
- `K05` [[kernel/K05 Terminology Standard|Terminology Standard]]: proper-noun extraction, aliases, reuse, and emerging terminology.
- `K06` [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: user hypotheses / source leads, the source-to-knowledge pipeline, synthesis, graph impact, and promotion.
- `K07` [[kernel/K07 Sources and Accuracy Standard|Sources and Accuracy Standard]]: source roles, claims, formulas, metrics, and freshness verification.
- `K08` [[kernel/K08 Metadata and Status Standard|Metadata and Status Standard]]: type, domain, priority, authoring / expression / learning status, coverage disposition, and evidence maturity.
- `K09` [[kernel/K09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]: body links, structural navigation, path, alias, and verification.
- `K10` [[kernel/K10 Writing and Formatting Standard|Writing and Formatting Standard]]: naming, formulas, tables, diagrams, rendering workflow, and the reader-facing language binding provided by `Language Contract`.
- `K11` [[kernel/K11 Expression Layer Standard|Expression Layer Standard]]: expression artifacts, coverage, readiness, evidence binding, and migration audit; concrete artifact bindings are registered by the `Expression Layer Entry`.
- `K12` [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]: single-note, batch, Guidance / Coverage reconciliation, module, source promotion, tiered rendering, and Terminal Audit; extension QA dimensions, scans, and gates are activated by the `Audit Dimension Registry`, the `Registered Scan Registry`, and the `Routing And Gate Registry` respectively; which receipt dimension each judgment item files under is fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|K12/08]].
- `K13` [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control Standard]]: Task Contract, time semantics, task state, Guidance/Amendment, Progress Ledger, Required Queue, batch admission/integration, completion, handoff, and recovery.

## Cross-domain Rule Registry

The following high-risk objects have a single canonical owner corpus-wide. Modifying these objects means modifying only the owner file; every other location MAY reference them only via Wiki Link or a registered slot, and MUST NOT copy the content (whether or not slightly rephrased).

| Object | Canonical owner |
|---|---|
| Kernel runtime route membership and route-to-Read-Set binding | [[kernel/Read Sets/Read Sets Index|Read Sets Index]] |
| Task-to-route combinations | [[kernel/K00 Standards Control/02 Task Routing|Task Routing]] |
| Runtime Card ownership, loading order, and source read-back protocol | [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]] |
| Runtime namespace startup and interrupted-state recovery | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate|Runtime Startup Gate]] |
| Large-scale creation, move, or deletion admission | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate|Large-scale Pre-execution Gate]] |
| M-tier page acceptance checklist | [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist|M-tier Gate Checklist]] |
| Terminal Proof formula | [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy|Completion Policy]] |
| Terminal Audit procedure and finding convergence | [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]] |
| Terminal Proof field contract and deterministic completion gate | [[kernel/K12 Quality Assurance/16 Terminal Proof Contract|Terminal Proof Contract]] |
| `task_state` vocabulary | [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|Task State and Transition Rules]] |
| Required Queue schema, revisions, batch lifecycle, and holds | [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|Required Queue Contract and Lifecycle]] |
| Queue transition authority, concurrency, write partition, and serial integration | [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]] |
| Guidance classification and impact | [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis|Guidance Classification and Impact Analysis]] |
| Guidance disposition and safe switching | [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching|Guidance Disposition and Safe Switching]] |
| Amendment record and controlled replanning | [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning|Amendment Log and Controlled Replanning]] |
| authoring / expression / learning status vocabularies | [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]] + `Expression Status Axis` role |
| `evidence_maturity` definition | [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]] |
| Evidence roles | [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Source Note / Research Synthesis templates | [[kernel/K06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles|Intake Note Types and Source Roles]] |
| Evaluation provenance element list | [[kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality|Evaluation and Source Quality]] |
| Official source policy | [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification|Official and Cross-source Verification]] |
| Reader-facing language policy | `Language Contract` slot |
| Expression-layer language policy | `Language Contract` slot + `Expression Layer Entry` registry |
| Deep-dive expression skeleton | `Expression Layer Entry` registry |
| Batch acceptance checklist | [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]] |
| Module and Coverage acceptance checklist | [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] |
| Source-to-Knowledge pipeline | [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Freshness and volatility vocabulary | [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] |
| Retirement and merge procedure | [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]] |
| Maintenance-run budget envelope | [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]] |
| Judgment item to receipt dimension map | [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]] |
