## Purpose

This file is the overall semantic index for the active Kernel. Detailed rules
are maintained by folder-based leaf modules. Task selection, loading, delivery,
and adopter runtime state are outside this index and do not become Kernel rules
by being linked from it.

## K00 Control Module Index

| Module | Responsibility |
|---|---|
| [[kernel/K00 Standards Control/02 Task Routing\|Task Routing]] | shared task-intent classifications and their stable Route IDs |
| [[kernel/K00 Standards Control/03 Standards Governance\|Standards Governance]] | governance process and the external adopter-state contract |
| [[kernel/K00 Standards Control/04 Control State and Scope\|Control State and Scope]] | protected control state and modification authority |
| [[kernel/K00 Standards Control/05 Core Principles\|Core Principles]] | universal knowledge-corpus principles |
| [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract\|Completion Precedence and Task Contract]] | precedence, contract, and selected completion semantics |
| [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota\|Effort Tiering and Priority Quota]] | S/M/L effort and priority constraints |
| [[kernel/K00 Standards Control/08 Maintenance Run Envelope\|Maintenance Run Envelope]] | bounded maintenance budget and candidate handling |
| [[kernel/K00 Standards Control/09 Default Constraints Snapshot\|Default Constraints Snapshot]] | kernel defaults consumed by task contracts |
| [[kernel/K00 Standards Control/11 Standards Map and Rule Registry\|Standards Map and Rule Registry]] | canonical content-rule ownership |
| [[kernel/K00 Standards Control/12 Control Registry\|Control Registry]] and [`control-registry.yaml`](<K00 Standards Control/control-registry.yaml>) | control-gate semantics plus the sole current machine registry for receipt selectors, producer positions, and revalidation projection |
| [[kernel/K00 Standards Control/13 Runtime Admission and Recovery\|Runtime Admission and Recovery]] | runtime startup/recovery and large-scale pre-execution admission |
| [[kernel/K00 Standards Control/17 Profile Dependency Closure\|Profile Dependency Closure]] | the typed single-Profile closure resolved by `profile-load` |
| [[kernel/K00 Standards Control/19 Profile Extension Interface\|Profile Extension Interface]] | common Profile extension points, binding semantics, and their machine interface registry |

## Standard Module Index

| Module ID | Stable MOC | Responsibility |
|---|---|---|
| `K00` | [[kernel/K00 Standards Overview\|Standards Overview]] | overall Kernel index, governance invariants, runtime admission/recovery, and Standards control |
| `K01` | [[kernel/K01 Scope and Architecture Standard\|Scope and Architecture]] | scope, logical architecture, knowledge spine, and foundation preservation |
| `K02` | [[kernel/K02 Knowledge Work Construction Standard\|Knowledge Work Construction]] | inventory, Coverage reconciliation, Corpus Planning lifecycle and artifact contracts, architecture, knowledge-batch production, and migration safety |
| `K03` | [[kernel/K03 Note Types and Ownership Standard\|Note Types and Ownership]] | note type, canonical owner, split, and duplication |
| `K04` | [[kernel/K04 Content Depth Standard\|Content Depth]] | concept, flow, system, production, evidence, and failure depth |
| `K05` | [[kernel/K05 Terminology Standard\|Terminology]] | term extraction, ownership, aliases, context, and reuse |
| `K06` | [[kernel/K06 Knowledge Intake and Evolution Standard\|Knowledge Intake and Evolution]] | source-to-knowledge, claims, promotion, and evolution |
| `K07` | [[kernel/K07 Sources and Accuracy Standard\|Sources and Accuracy]] | source authority, evidence role, verification, provenance, and uncertainty |
| `K08` | [[kernel/K08 Metadata and Status Standard\|Metadata and Status]] | frontmatter, vocabulary, status axes, evidence, and migration metadata |
| `K09` | [[kernel/K09 Wiki Link and Navigation Standard\|Wiki Link and Navigation]] | semantic links, MOC, path, alias, heading, and graph verification |
| `K10` | [[kernel/K10 Writing and Formatting Standard\|Writing and Formatting]] | naming, prose, math, tables, code, diagrams, assets, and rendering; reader-facing language is provided by the `Language Contract` |
| `K11` | [[kernel/K11 Expression Layer Standard\|Expression Layer]] | expression artifacts, canonical knowledge separation, readiness, and migration interface |
| `K12` | [[kernel/K12 Quality Assurance Standard\|Quality Assurance]] | note, module, batch, source, expression, audit evidence reuse and invalidation, content-level propagation, substantive correctness, active-task Standards adoption, rendering, and terminal gates |
| `K13` | [[kernel/K13 Task Runtime and Execution Control Standard\|Task Runtime and Execution Control]] | task contract, state, Guidance/Amendment, Progress, Required Queue, hash-bound batch Work Specs, batch control, controlled Standards-adoption state writes, completion, and recovery |

## Related

- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
