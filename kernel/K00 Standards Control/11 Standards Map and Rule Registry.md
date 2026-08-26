## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Previous: [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].
- Next: [[kernel/K00 Standards Control/12 Control Registry|Control Registry]].

## Standards Map

- `K00` [[kernel/K00 Standards Overview|Standards Overview]] and [[kernel/K00 Standards Control/03 Standards Governance|Standards Control]]: Kernel entry, precedence, governance invariants, defaults, and control registries.
- `K01` [[kernel/K01 Scope and Architecture Standard|Scope and Architecture Standard]]: generic scope boundaries, foundation preservation, logical architecture, structural unit and support layer interfaces with their `Structure Registry` binding, and the concrete scope binding provided by `Profile Scope`.
- `K02` [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction Standard]]: inventory, Coverage reconciliation, corpus-planning artifacts, architecture and dependency planning, knowledge-batch production, and migration safety.
- `K03` [[kernel/K03 Note Types and Ownership Standard|Note Types and Ownership Standard]]: note types, Process / Flow, canonical ownership, split, and duplication.
- `K04` [[kernel/K04 Content Depth Standard|Content Depth Standard]]: Atomic / Core / System depth, Process / Flow, system chains, and evaluation provenance.
- `K05` [[kernel/K05 Terminology Standard|Terminology Standard]]: proper-noun extraction, aliases, reuse, and emerging terminology.
- `K06` [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]: user hypotheses / source leads, the source-to-knowledge pipeline, synthesis, graph impact, and promotion.
- `K07` [[kernel/K07 Sources and Accuracy Standard|Sources and Accuracy Standard]]: source roles, claims, formulas, metrics, and freshness verification.
- `K08` [[kernel/K08 Metadata and Status Standard|Metadata and Status Standard]]: type, domain, priority, authoring / expression / learning status, coverage disposition, evidence maturity, field applicability modes, writer and projection authority, relationship metadata, and the page boundary contract with their `Metadata Contract` binding.
- `K09` [[kernel/K09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]: body links, structural navigation, path, alias, and verification.
- `K10` [[kernel/K10 Writing and Formatting Standard|Writing and Formatting Standard]]: naming, formulas, tables, diagrams, rendering workflow, and the reader-facing language binding provided by `Language Contract`.
- `K11` [[kernel/K11 Expression Layer Standard|Expression Layer Standard]]: expression artifacts, coverage, readiness, evidence binding, and migration audit; concrete artifact bindings are registered by the `Expression Layer Entry`.
- `K12` [[kernel/K12 Quality Assurance Standard|Quality Assurance Standard]]: single-note, batch, Guidance / Coverage reconciliation, module, source promotion, audit evidence reuse and invalidation, content-level propagation, substantive correctness review, active-task Standards adoption semantics, tiered rendering, and Terminal Audit; extension QA dimensions, scans, and gates are activated by the `Audit Dimension Registry`, the `Registered Scan Registry`, and the `Routing And Gate Registry` respectively; which receipt dimension each judgment item files under is fixed by [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map|K12/08]] and [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map|K12/18]].
- `K13` [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control Standard]]: Task Contract, time semantics, task state, Guidance/Amendment, Progress Ledger, Required Queue, batch admission/integration, controlled Standards-adoption state writes, completion, handoff, recovery, and the escalation contract.

## Cross-domain Rule Registry

The following high-risk objects have a single canonical owner corpus-wide. Modifying these objects means modifying only that owner. A non-owner may relate to a registered object in exactly one of two ways:

- **Reference** — a Wiki Link or a registered slot, carrying no rule content of its own. Always permitted.
- **Derived projection** — a bounded selection, explanation, compression, or generated view. It MUST identify the canonical owner, MUST NOT change the owner's conditions, strength, exceptions, or verdict, and MUST NOT present an omitted subset as complete.

When a complete closed contract can be derived deterministically, it is generated from its machine owner instead of being maintained as a second hand-written specification. A selective projection may omit material, but every rule it does state retains the conditions, qualifiers, and exceptions needed to avoid changing its meaning. When a projection and its owner disagree, the owner prevails and the projection is corrected, never the reverse.

This registry governs rule text. The three conditions do not authorize a view of mutable control-plane state — Coverage, Queue, Progress, receipts, holds, or fingerprints. Each such view is governed by that state's own owner; for the Progress Ledger see [[kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract|Progress Ledger Contract]].

| Object | Canonical owner |
|---|---|
| Task-to-route combinations | [[kernel/K00 Standards Control/02 Task Routing\|Task Routing]] |
| Common Profile extension points and binding interface | [[kernel/K00 Standards Control/19 Profile Extension Interface\|Profile Extension Interface]] |
| Candidate and selected Profile dependency closure | [[kernel/K00 Standards Control/17 Profile Dependency Closure\|Profile Dependency Closure]] |
| Runtime namespace startup and interrupted-state recovery | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Runtime Startup Gate\|Runtime Startup Gate]] |
| Large-scale creation, move, or deletion admission | [[kernel/K00 Standards Control/13 Runtime Admission and Recovery#Large-scale Pre-execution Gate\|Large-scale Pre-execution Gate]] |
| Task Contract decision list and what a task freezes | [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Task Contract Decisions\|Task Contract Decisions]] |
| Structural unit kinds, module admission, role implementation modes, and the Structure Registry ownership boundary | [[kernel/K01 Scope and Architecture/05 Structural Unit Interface\|Structural Unit Interface]] |
| Support layer structural interfaces: shared base, layouts, and role-specific bindings | [[kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces\|Support Layer Structural Interfaces]] |
| Corpus Planning applicability, lifecycle, and reconciliation | [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle\|Corpus Planning Applicability and Lifecycle]] |
| Corpus Planning runtime, audit, deterministic-check, receipt, and affected-path boundaries | [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries\|Corpus Planning Runtime Audit and Gate Boundaries]] |
| `Global Map` exact role and record contract | [[kernel/K02 Knowledge Work Construction/05 Global Map Contract\|Global Map Contract]] |
| `Capability Matrix` exact role and record contract | [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract\|Capability Matrix Contract]] |
| `Gap Register` exact role and record contract | [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract\|Gap Register Contract]] |
| M-tier page acceptance checklist | [[kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review#M-tier Gate Checklist\|M-tier Gate Checklist]] |
| Terminal Proof formula | [[kernel/K13 Task Runtime and Execution Control/11 Completion Policy\|Completion Policy]] |
| Terminal Audit procedure and finding convergence | [[kernel/K12 Quality Assurance/15 Terminal Audit and Convergence\|Terminal Audit and Convergence]] |
| Terminal Proof field contract and deterministic completion gate | [[kernel/K12 Quality Assurance/16 Terminal Proof Contract\|Terminal Proof Contract]] |
| `task_state` membership, classes, completion-semantics applicability, and transition catalogs | `kernel/K13 Task Runtime and Execution Control/runtime-state-model.json`; state meanings and invariants remain with [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules\|Task State and Transition Rules]] |
| Required Queue state, hold, execution-mode, and transition membership | `kernel/K13 Task Runtime and Execution Control/runtime-state-model.json`; state meanings and lifecycle invariants remain with [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle\|Required Queue Contract and Lifecycle]] |
| Required Queue record schema, revision semantics, and Work Spec binding | [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle\|Required Queue Contract and Lifecycle]] |
| Simple/complex Batch Work Spec declaration, managed binding, immutability, and Queue ownership boundary | [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle#Batch Work Specification Binding\|Batch Work Specification Binding]] |
| Queue compilation, same-scope replanning, writer transaction scope, and the human Queue view | [[kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views\|Queue Compilation Replanning and Views]] |
| Queue transition authority, concurrency, write partition, and serial integration | [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration\|Batch Admission Transitions and Serial Integration]] |
| Execution role vocabulary: `agent`, `subagent`, and `integrator` | [[kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace#Execution Roles\|Execution Roles]] |
| Active-task Standards adoption semantics, changed-predicate scope, evidence invalidation, and required gate reruns | [[kernel/K12 Quality Assurance/10 Standards Version Adoption\|Standards Version Adoption]] |
| Active-task Standards adoption state-write and interrupted-transaction boundary | [[kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction\|Standards Adoption State Transaction]] |
| Initial planning state-write: the one transaction that fills an empty runtime namespace, and where it stops | [[kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction\|Initial Task Planning Transaction]] |
| Contract policy-exception register and the guarded Contract Amendment state-write | [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning\|Amendment Log and Controlled Replanning]] |
| Exceptable policy IDs, owner references, limit domains, defaults, and effective-policy fingerprint payload | `kernel/K00 Standards Control/contract-exception-policy-base.yaml`; each row retains the semantic owner it names |
| Resume `next_action` token vocabulary | [[kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary\|Resume Next Action Vocabulary]] |
| Escalation contract: which conditions oblige suspending a run and handing the decision to a person | [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy\|Escalation Policy]] |
| Guidance classification and impact | [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis\|Guidance Classification and Impact Analysis]] |
| Guidance disposition/status membership and finality | `kernel/K13 Task Runtime and Execution Control/runtime-state-model.json`; meanings and safe-switching invariants remain with [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching\|Guidance Disposition and Safe Switching]] |
| Amendment status membership, status/write-back finality, and operational operation-to-capability mapping | `kernel/K13 Task Runtime and Execution Control/runtime-state-model.json`; Amendment-record meaning and controlled-replanning invariants remain with [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning\|Amendment Log and Controlled Replanning]] |
| authoring / expression / learning status vocabularies | [[kernel/K08 Metadata and Status/03 Status Axes\|Status Axes]] + `Expression Status Axis` role |
| `coverage_disposition` vocabulary and its scope semantics | [[kernel/K08 Metadata and Status/03 Status Axes#Coverage Disposition\|Coverage Disposition]] |
| `evidence_maturity` definition | [[kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata\|Evidence and Relationship Metadata]] |
| Frontmatter applicability modes, two-layer composition, and the unknown-field closure | [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract\|Frontmatter Applicability Contract]] |
| Frontmatter writer, projection, and derived-persistence authority | [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority\|Frontmatter Writer and Projection Authority]] |
| Page relationship field names, directions, targets, and value shapes | [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract\|Relationship Metadata Contract]] |
| Page boundary contract: the `boundary` block schema, cross-page resolvability, reciprocity, and uniqueness rules, and the boundary projection authority with its display labels | [[kernel/K08 Metadata and Status/09 Page Boundary Contract\|Page Boundary Contract]] |
| Evidence roles | [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline\|Source-to-Knowledge Pipeline]] |
| Source Note / Research Synthesis templates | [[kernel/K06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles\|Intake Note Types and Source Roles]] |
| Evaluation provenance element list | [[kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality\|Evaluation and Source Quality]] |
| Official source policy | [[kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification\|Official and Cross-source Verification]] |
| Reader-facing language policy | `Language Contract` slot |
| Expression-layer language policy | `Language Contract` slot + `Expression Layer Entry` registry |
| Deep-dive expression skeleton | `Expression Layer Entry` registry |
| Batch acceptance checklist | [[kernel/K12 Quality Assurance/14 Batch Review\|Batch Review]] |
| Batch-close Closed List membership and order | `kernel/K12 Quality Assurance/batch-close-closed-list.yaml`; semantics and boundary explanation remain owned by [[kernel/K12 Quality Assurance/09 Batch-close Closed List#Batch-close Closed List\|Batch-close Closed List]] |
| Module and Coverage acceptance checklist | [[kernel/K12 Quality Assurance/03 Module and Coverage Review\|Module and Coverage Review]] |
| Source-to-Knowledge pipeline | [[kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline\|Source-to-Knowledge Pipeline]] |
| Freshness and volatility vocabulary | [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata\|Review Source and Migration Metadata]] |
| Retirement and merge procedure | [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy\|Split and Duplication Policy]] |
| Maintenance-run budget envelope | [[kernel/K00 Standards Control/08 Maintenance Run Envelope\|Maintenance Run Envelope]] |
| Closed membership of the profile-overridable execution defaults and of the constitutional constants | `kernel/K00 Standards Control/execution-defaults-base.yaml`, registered by [[kernel/K00 Standards Control/09 Default Constraints Snapshot\|Default Constraints Snapshot]] |
| Judgment item to receipt dimension map, Single Note Review layer | [[kernel/K12 Quality Assurance/08 Judgment Item Dimension Map\|Judgment Item Dimension Map]] |
| Judgment item to receipt dimension map above one page, and the receipt dimension of a control-plane Gate | [[kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map\|Cross-page and Control-plane Dimension Map]] |
| Gate receipt payload and `manual-attestation` recording authority | [[kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract\|Gate Receipt Payload Contract]] |
| Batch `AuditPlan` generation and the incremental-by-default check scope | [[kernel/K12 Quality Assurance/19 Incremental Audit Planning\|Incremental Audit Planning]] |
