## Purpose

This file is the sole overall entry point for the active Standards. It is responsible only for state slots, task routing, the domain index, and the loading protocol; detailed rules are maintained by folder-based leaf modules.

## Current State

| Field | Value |
|---|---|
| Standards version | `{{standards_version}}` (provided by the active governance state) |
| Status | `{{standards_status}}` (provided by the active governance state) |
| Effective date | `{{effective_date}}` (provided by the active governance state) |
| Domain MOCs | `derived-from-active-kernel-domain-registry` |
| Canonical leaf modules | `derived-from-active-kernel-inventory` |
| Routing model | Kernel Runtime Cards (Card-first) + Read Sets escalation read-back + Triggered / Gate Modules |
| Change authority | User's explicit governance instruction |

The complete state rules are maintained by [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].

## Start Here

```text
Open Standards Overview
 -> Open The Kernel Card Index And Load Task Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Record Standards Version And Loaded Set
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract
 -> Execute One Verifiable Batch
 -> Run Gate Checks And Scripts
```

1. All tasks enter through the kernel-owned [[kernel/Cards/00 Card Index|Card Index]], then load the Core Bootstrap Card and the Runtime Card corresponding to the task. A selected profile cannot replace or disable these cards.
2. In exception cases (card does not cover the situation, rule disputes, L-tier depth rules, Governance tasks), read back Read Sets and leaf modules per [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|00/01]].
3. When reading back, load only the leaf modules needed by the current event and the current gate.
4. MOCs are for locating; using one does not mean all rules within it have been read.
5. Long-running tasks MUST combine the content Card with the kernel-owned [[kernel/Cards/07 Long-running Execution Card|Long-running Execution Card]].
6. Completion candidates MUST combine the kernel-owned [[kernel/Cards/08 Audit and Completion Card|Audit and Completion Card]]; Governance tasks MUST read the [[kernel/Read Sets/09 Standards Governance Read Set|RS 09]] source text in full.

Runtime Cards are kernel-owned compiled artifacts of the Read Sets (the Standards source text is the source code; the cards are compiled artifacts). Cards take precedence for routine tasks; exception cases read back the source text — see Card-first Reading Mode in [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|00/01]]. A profile may register an additional domain route or gate, but that extension is loaded alongside the kernel cards and cannot override their IDs, replace their rules, or make them optional.

## Task Router

| Task | Primary route |
|---|---|
| Create or extend a canonical note | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] |
| Build a complete knowledge module, process system, or application system slice | [[kernel/Read Sets/03 Module Build Read Set\|Module Build]] |
| Extend knowledge from official docs, papers, code, cases, or community information | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] |
| Create, migrate, or review expression-layer content | The `Expression Layer Read Set` registered in the selected profile's `Routing And Gate Registry` |
| Move, rename, split, merge, or directory restructuring | [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] |
| Multi-batch, sustained execution, checkpoint, or resume | [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]] |
| Review, Completion Gate, or Terminal Audit | [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]] |
| Modify Standards, Read Sets, version, or control-plane structure | [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance]] |
| Mid-task guidance, scope, priority, or correction | [[kernel/02 Build Execution/02 Mid-task Guidance and Amendment\|Mid-task Guidance and Amendment]] |

Periodic knowledge-base update and freshness tasks go through the kernel-owned [[kernel/Cards/10 Maintenance Run Card|Maintenance Run Card]], with [[kernel/Read Sets/10 Maintenance Run Read Set|RS 10]] used for source read-back.

Detailed task combinations and the Pre-execution Gate are located in [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].

## Domain Index

| Domain | Stable MOC | Responsibility |
|---|---|---|
| `00` | [[kernel/00 Standards Overview\|Standards Overview]] | overall Index, Kernel Card and Read Set routing, and Standards control |
| `01` | [[kernel/01 Scope and Architecture Standard\|Scope and Architecture]] | scope, logical architecture, knowledge spine, and foundation preservation |
| `02` | [[kernel/02 Knowledge Base Build Execution Standard\|Build Execution]] | task contract, state, guidance, batch, checkpoint, resume, and handoff |
| `03` | [[kernel/03 Note Types and Ownership Standard\|Note Types and Ownership]] | note type, canonical owner, split, and duplication |
| `04` | [[kernel/04 Content Depth Standard\|Content Depth]] | concept, flow, system, production, evidence, and failure depth |
| `05` | [[kernel/05 Terminology Standard\|Terminology]] | term extraction, ownership, aliases, context, and reuse |
| `06` | [[kernel/06 Knowledge Intake and Evolution Standard\|Knowledge Intake and Evolution]] | source-to-knowledge, claims, promotion, and evolution |
| `07` | [[kernel/07 Sources and Accuracy Standard\|Sources and Accuracy]] | source authority, evidence role, verification, provenance, and uncertainty |
| `08` | [[kernel/08 Metadata and Status Standard\|Metadata and Status]] | frontmatter, vocabulary, status axes, evidence, and migration metadata |
| `09` | [[kernel/09 Wiki Link and Navigation Standard\|Wiki Link and Navigation]] | semantic links, MOC, path, alias, heading, and graph verification |
| `10` | [[kernel/10 Writing and Formatting Standard\|Writing and Formatting]] | naming, prose, math, tables, code, diagrams, assets, and rendering; reader-facing language is provided by the `Language Contract` |
| `11` | [[kernel/11 Expression Layer Standard\|Expression Layer]] | expression artifacts, canonical knowledge separation, readiness, and migration interface |
| `12` | [[kernel/12 Quality Assurance Standard\|Quality Assurance]] | note, module, batch, source, expression, rendering, and terminal gates |

## Loading Contract

- `Domain MOC`: states which modules the domain contains, the original section owners, and the applicable Read Sets.
- `Leaf module`: owns the rule text; the unit that actually needs to be read during execution.
- `Runtime Card`: kernel-owned compiled execution guidance for a routine task; it compresses a Read Set but never owns rule text.
- `Read Set`: maps task phases to leaf modules and is the first source read-back boundary.
- `Triggered module`: loaded only when conditions such as guidance, source, diagram, or migration arise.
- `Gate module`: loaded before a note, batch, module, or task closes.
- `loaded set`: the actual kernel Runtime Card IDs and paths, any profile extension route explicitly combined with them, and module paths read back on escalation, recorded in the Task Contract; a broad `02` or `12` alone MUST NOT be written.

Module splitting does not change rule precedence. Conflicts are still resolved per [[kernel/00 Standards Control/06 Completion Precedence and Task Contract#Standard Precedence|Standard Precedence]].

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

The complete default constraints are located in the [[kernel/00 Standards Control/09 Default Constraints Snapshot|Default Constraints Snapshot]].

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]]
- [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
- [[kernel/12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]
