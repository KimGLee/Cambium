## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/10 Batch Execution Checklist|Batch Execution Checklist]].
- Next: [[kernel/00 Standards Control/12 Control Registry|Control Registry]].

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
- `12` [[kernel/12 Quality Assurance Standard|Quality Assurance Standard]]: single-note, batch, Guidance / Coverage reconciliation, module, source promotion, tiered rendering, and Terminal Audit; extension QA dimensions, scans, and gates are activated by the `Audit Dimension Registry`, the `Registered Scan Registry`, and the `Routing And Gate Registry` respectively; which receipt dimension each judgment item files under is fixed by [[kernel/12 Quality Assurance/08 Judgment Item Dimension Map|08]].

## Cross-domain Rule Registry

The following high-risk objects have a single canonical owner corpus-wide. Modifying these objects means modifying only the owner file; every other location MAY reference them only via Wiki Link or a registered slot, and MUST NOT copy the content (whether or not slightly rephrased).

| Object | Canonical owner |
|---|---|
| Terminal Proof formula | [[kernel/02 Build Execution/07 Completion and Handoff|Completion and Handoff]] |
| Terminal Audit procedure and Proof field list | [[kernel/12 Quality Assurance/15 Terminal Audit and Convergence|Terminal Audit and Convergence]] |
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
| Batch acceptance checklist | [[kernel/12 Quality Assurance/14 Batch Review|Batch Review]] |
| Module and Coverage acceptance checklist | [[kernel/12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] |
| Source-to-Knowledge pipeline | [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] |
| Freshness and volatility vocabulary | [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] |
| Retirement and merge procedure | [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]] |
| Maintenance-run budget envelope | [[kernel/00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]] |
| Judgment item to receipt dimension map | [[kernel/12 Quality Assurance/08 Judgment Item Dimension Map|Judgment Item Dimension Map]] |
