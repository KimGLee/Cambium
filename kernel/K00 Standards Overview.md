## Purpose

This file is the sole overall entry point for the active Standards. It is responsible only for state slots, task routing, the Standard Module Index, and the loading protocol; detailed rules are maintained by folder-based leaf modules.

## Current State

| Field | Value |
|---|---|
| Standards version | See [[kernel/K00 Standards Control/03 Standards Governance#Standards Control\|active Standards state]] |
| Status | See [[kernel/K00 Standards Control/03 Standards Governance#Standards Control\|active Standards state]] |
| Effective date | See [[kernel/K00 Standards Control/03 Standards Governance#Standards Control\|active Standards state]] |
| Selected profile manifest | See [[kernel/K00 Standards Control/03 Standards Governance#Standards Control\|active Standards state]] |
| Standard module MOCs | `derived-from-active-kernel-module-registry` |
| Canonical leaf modules | `derived-from-active-kernel-inventory` |
| Routing model | Kernel Runtime Cards (Card-first) + Read Sets escalation read-back + Triggered / Gate Modules |
| Change authority | User's explicit governance instruction |

The complete state rules are maintained by [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]].

## Start Here

```text
Open Standards Overview
 -> Open The Kernel Card Index And Load Task Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Apply Runtime Startup Or Recovery Gate
 -> Record Standards Version, Selected Profile Manifest, And Loaded Set
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract
 -> Execute One Verifiable Batch
 -> Run Gate Checks And Scripts
```

1. All tasks enter through the kernel-owned [[kernel/Cards/Card Index|Card Index]], then load the Core Bootstrap Card and the Runtime Card corresponding to the task. A selected profile cannot replace or disable these cards.
2. In exception cases (card does not cover the situation, rule disputes, L-tier depth rules, Governance tasks), read back Read Sets and leaf modules per [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|K00/01]].
3. When reading back, load only the leaf modules needed by the current event and the current gate.
4. MOCs are for locating; using one does not mean all rules within it have been read.
5. Large-scale creation, moves, or deletion MUST pass the kernel-owned [[kernel/Cards/R11 Large-scale Work Admission Card|Large-scale Work Admission Card]] before execution begins.
6. Long-running tasks MUST combine the content Card with the kernel-owned [[kernel/Cards/R07 Long-running Execution Card|Long-running Execution Card]].
7. Targeted or specialized audits MUST combine the affected task route with the kernel-owned [[kernel/Cards/R12 Targeted and Specialized Audit Card|Targeted and Specialized Audit Card]].
8. Task completion candidates MUST combine the kernel-owned [[kernel/Cards/R08 Audit and Completion Card|Audit and Completion Card]]; Governance tasks MUST read the [[kernel/Read Sets/R09 Standards Governance Read Set|R09 Read Set]] source text in full.

Runtime Cards are kernel-owned compiled artifacts of the Read Sets (the Standards source text is the source code; the cards are compiled artifacts). Cards take precedence for routine tasks; exception cases read back the source text — see Card-first Reading Mode in [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|K00/01]]. `Kxx` identifies a Standards module; `Rxx` identifies a runtime route. These namespaces are independent and their matching numbers imply nothing. A profile may register a namespaced supplemental route or gate, but it loads alongside the kernel route and cannot reuse an Rxx identity, replace a kernel rule, or make a kernel route optional.

## Task Router

| Task | Primary route |
|---|---|
| Create or extend a canonical note | [[kernel/Read Sets/R02 Single Note Authoring Read Set\|Single Note Authoring]] |
| Build a complete knowledge module, process system, or application system slice | [[kernel/Read Sets/R03 Module Build Read Set\|Module Build]] |
| Extend knowledge from official docs, papers, code, cases, or community information | [[kernel/Read Sets/R04 Source-driven Expansion Read Set\|Source-driven Expansion]] |
| Create, migrate, or review expression-layer content | [[kernel/Read Sets/R05 Expression Layer Read Set\|R05 Expression Layer]], plus the selected profile's concrete artifact binding and any supplemental gate |
| Move, rename, split, merge, or directory restructuring | [[kernel/Read Sets/R06 Migration and Refactor Read Set\|Migration and Refactor]] |
| Admit large-scale creation, moves, or deletion to execution | [[kernel/Read Sets/R11 Large-scale Work Admission Read Set\|Large-scale Work Admission]], plus the route for the actual work |
| Multi-batch, sustained execution, checkpoint, or resume | [[kernel/Read Sets/R07 Long-running Execution Read Set\|Long-running Execution]] |
| Run a targeted or specialized audit | [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set\|Targeted and Specialized Audit]], plus the route relevant to the finding |
| Enter the task Completion Gate or Terminal Audit | [[kernel/Read Sets/R08 Audit and Completion Read Set\|Audit and Completion]] |
| Modify Standards, Read Sets, version, or control-plane structure | [[kernel/Read Sets/R09 Standards Governance Read Set\|Standards Governance]] |
| Mid-task guidance, scope, priority, or correction | [[kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis\|Guidance Classification and Impact Analysis]] + [[kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching\|Guidance Disposition and Safe Switching]] + [[kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning\|Amendment Log and Controlled Replanning]] |

Periodic knowledge-base update and freshness tasks go through the kernel-owned [[kernel/Cards/R10 Maintenance Run Card|Maintenance Run Card]], with [[kernel/Read Sets/R10 Maintenance Run Read Set|R10 Read Set]] used for source read-back.

Detailed task combinations are located in [[kernel/K00 Standards Control/02 Task Routing|Task Routing]]. Runtime-state startup/recovery and the large-scale admission gate are owned by [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|Runtime Admission and Recovery]].

## K00 Control Module Index

| Module | Responsibility |
|---|---|
| [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol\|Operating Role and Reading Protocol]] | execution role, Card-first loading, and source read-back |
| [[kernel/K00 Standards Control/02 Task Routing\|Task Routing]] | task-to-route combinations only |
| [[kernel/K00 Standards Control/03 Standards Governance\|Standards Governance]] | active adopter state and governance change process |
| [[kernel/K00 Standards Control/04 Control State and Scope\|Control State and Scope]] | protected control state and modification authority |
| [[kernel/K00 Standards Control/05 Core Principles\|Core Principles]] | universal knowledge-corpus principles |
| [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract\|Completion Precedence and Task Contract]] | precedence, contract, and selected completion semantics |
| [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota\|Effort Tiering and Priority Quota]] | S/M/L effort and priority constraints |
| [[kernel/K00 Standards Control/08 Maintenance Run Envelope\|Maintenance Run Envelope]] | bounded maintenance budget and candidate handling |
| [[kernel/K00 Standards Control/09 Default Constraints Snapshot\|Default Constraints Snapshot]] | kernel defaults consumed by task contracts |
| [[kernel/K00 Standards Control/10 Batch Execution Checklist\|Batch Execution Checklist]] | batch execution entry and close checklist |
| [[kernel/K00 Standards Control/11 Standards Map and Rule Registry\|Standards Map and Rule Registry]] | canonical content-rule ownership |
| [[kernel/K00 Standards Control/12 Control Registry\|Control Registry]] | canonical control-gate ownership |
| [[kernel/K00 Standards Control/13 Runtime Admission and Recovery\|Runtime Admission and Recovery]] | runtime startup/recovery and large-scale pre-execution admission |

## Standard Module Index

| Module ID | Stable MOC | Responsibility |
|---|---|---|
| `K00` | [[kernel/K00 Standards Overview\|Standards Overview]] | overall Index, Kernel Card and Read Set routing, runtime admission/recovery, and Standards control |
| `K01` | [[kernel/K01 Scope and Architecture Standard\|Scope and Architecture]] | scope, logical architecture, knowledge spine, and foundation preservation |
| `K02` | [[kernel/K02 Knowledge Work Construction Standard\|Knowledge Work Construction]] | inventory, Coverage reconciliation, architecture, knowledge-batch production, and migration safety |
| `K03` | [[kernel/K03 Note Types and Ownership Standard\|Note Types and Ownership]] | note type, canonical owner, split, and duplication |
| `K04` | [[kernel/K04 Content Depth Standard\|Content Depth]] | concept, flow, system, production, evidence, and failure depth |
| `K05` | [[kernel/K05 Terminology Standard\|Terminology]] | term extraction, ownership, aliases, context, and reuse |
| `K06` | [[kernel/K06 Knowledge Intake and Evolution Standard\|Knowledge Intake and Evolution]] | source-to-knowledge, claims, promotion, and evolution |
| `K07` | [[kernel/K07 Sources and Accuracy Standard\|Sources and Accuracy]] | source authority, evidence role, verification, provenance, and uncertainty |
| `K08` | [[kernel/K08 Metadata and Status Standard\|Metadata and Status]] | frontmatter, vocabulary, status axes, evidence, and migration metadata |
| `K09` | [[kernel/K09 Wiki Link and Navigation Standard\|Wiki Link and Navigation]] | semantic links, MOC, path, alias, heading, and graph verification |
| `K10` | [[kernel/K10 Writing and Formatting Standard\|Writing and Formatting]] | naming, prose, math, tables, code, diagrams, assets, and rendering; reader-facing language is provided by the `Language Contract` |
| `K11` | [[kernel/K11 Expression Layer Standard\|Expression Layer]] | expression artifacts, canonical knowledge separation, readiness, and migration interface |
| `K12` | [[kernel/K12 Quality Assurance Standard\|Quality Assurance]] | note, module, batch, source, expression, rendering, and terminal gates |
| `K13` | [[kernel/K13 Task Runtime and Execution Control Standard\|Task Runtime and Execution Control]] | task contract, state, Guidance/Amendment, Progress, Required Queue, batch control, completion, handoff, and recovery |

## Loading Contract

- `Standard Module MOC`: states which leaf modules the Kxx module family contains, the original section owners, and the applicable Read Sets.
- `Leaf module`: owns the rule text; the unit that actually needs to be read during execution.
- `Runtime Card`: kernel-owned compiled execution guidance for a routine task; it compresses a Read Set but never owns rule text.
- `Read Set`: maps task phases to leaf modules and is the first source read-back boundary.
- `Triggered module`: loaded only when conditions such as guidance, source, diagram, or migration arise.
- `Gate module`: loaded before a note, batch, module, or task closes.
- `selected profile manifest`: the single profile chosen by the active Standards state; the manifest path is frozen in the Task Contract and is not inferred from directories, generated artifacts, or profile IDs.
- `loaded set`: the selected Rxx route IDs and Runtime Card paths, any namespaced profile route explicitly combined with them, and every Read Set or leaf path actually read back, recorded in the Task Contract; a broad K-module identifier alone MUST NOT be written as proof of loading.

Module splitting does not change rule precedence. Conflicts are still resolved per [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]].

## Protected Defaults

- Active Standards are a protected control plane; only an explicit governance instruction MAY modify them.
- Folders, file names, body language, identity-reserved values, and first-occurrence term display forms are provided by the selected profile's `Language Contract`.
- A knowledge object has exactly one canonical owner; other pages reuse it via Wiki links.
- Do not roll back, overwrite, or delete user modifications whose origin cannot be confirmed.
- External sources MUST pass through claim extraction, evidence review, and promotion decision.
- Mid-task Guidance MUST enter the Amendment Log and does not rely on ephemeral context.
- Audit results MUST be bound to an acceptance predicate, artifact/dependency/contract fingerprints, and a verifier; valid receipts MAY be reused, and relevant changes MUST trigger dimension-specific invalidation.
- Standards splits and migrations MUST be reconciled block by block; rules MUST NOT be trimmed, summarized, or deleted under cover of structural adjustment.
- Rendering acceptance defaults to source parsing and deterministic static verification; interactive UI, screenshots, visual models, and screen recording MUST meet the graded escalation conditions.
- Completion MUST pass the applicable gates; time, file counts, and structural checks cannot alone prove completion.

The complete default constraints are located in the [[kernel/K00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
