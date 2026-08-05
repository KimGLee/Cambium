## Navigation

- Parent: [[kernel/K00 Standards Overview|K00 Standards Overview]].
- Next: [[kernel/K00 Standards Control/02 Task Routing|Task Routing]].

## Purpose

Active Standards define the content, structure, citation, source, expression-layer split, and quality acceptance rules for the selected `knowledge-host` corpus.

The goal of these Standards is not to increase file count, but to ensure the knowledge corpus can support:

- Systematic learning: knowing prerequisites, core mechanisms, and follow-on directions.
- Deep understanding: able to explain reasons, assumptions, boundaries, and failure modes.
- Engineering practice: able to discuss implementation, evaluation, reliability, safety, and cost.
- Long-term maintenance: one concept has a single source of truth, and content can be reused and updated.
- Continuous evolution: able to discover knowledge gaps from official articles, papers, cases, and community signals, and to safely extend the knowledge graph through evidence synthesis.

## Operating Role

[[kernel/K00 Standards Overview|K00 Standards Overview]] is the sole entry point and rule router for the entire Standards system. It is responsible for telling the executor:

- Which Standards the current task MUST read.
- The order in which to read the Standards.
- Which constraints are always in effect.
- When modification of the knowledge corpus MAY begin.
- Which acceptance checks MUST be passed before completion.

The overall Index does not replace the detailed rules. A long-running task MUST NOT read only `K00` and then execute directly; it MUST load the corresponding kernel runtime routes and Cards, with Read Sets and leaf modules read back in exception cases. Kxx module identities and Rxx route identities are separate namespaces.

## Mandatory Reading Protocol

Before any knowledge-corpus task starts, resolve rules in the following order:

```text
K00 Standards Overview
 -> Open The Kernel Card Index And Load Task Runtime Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract And Loaded Set
 -> Execute One Verifiable Batch
 -> Gate Checks And Scripts
```

All tasks enter through the kernel-owned [[kernel/Cards/Card Index|Card Index]], then load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]] and the Runtime Card corresponding to the task. When the source text needs to be read back, select the Read Set corresponding to the actual task from [[kernel/Read Sets/Read Sets Index|Read Sets Index]]; a task being a knowledge-corpus long-running task MUST NOT by itself cause automatic loading of all modules of `K01`, `K02`, `K08`, and `K12`.

A large-scale task MUST pass [[kernel/Cards/R11 Large-scale Work Admission Card|Large-scale Work Admission]] before execution begins. A long-running task MUST combine the Card corresponding to the actual content type with [[kernel/Cards/R07 Long-running Execution Card|Long-running Execution]]; when reading back the source text, combine the corresponding Read Sets. A targeted or specialized audit loads [[kernel/Cards/R12 Targeted and Specialized Audit Card|Targeted and Specialized Audit]], while a task completion candidate loads [[kernel/Cards/R08 Audit and Completion Card|Audit and Completion]]. Quality rules enter the contract at task start via the Gate list; the full gate procedure is read only when the corresponding checkpoint is reached.

The Task Contract or Progress Ledger MUST record:

- `standards_version`.
- `selected_profile_manifest`, copied exactly from the active Standards state.
- The actual loaded set: selected Rxx route IDs and Runtime Card paths, any namespaced profile route explicitly combined with them, and every Read Set or leaf path actually read back.
- The Runtime Cards used and the Read Sets actually read back.
- Gate modules registered but not yet triggered.
- Re-resolution results after Standards or task scope changes.

## Card-first Reading Mode

The default reading mode is to read the task's kernel Runtime Card. A Card is a faithful compression of the corresponding Read Set's Start/Triggered/Gate modules, covering the determinations, procedures, and Gate lists needed for routine tasks.

In the following cases the Standards source text MUST be read back; cards alone MUST NOT be relied on:

- The card does not cover the current situation, or the card content is in doubt.
- A rule dispute or rule conflict requires adjudication.
- Depth rules for L-tier pages (the complete list is maintained only in the source text).
- Governance tasks: the R09 Read Set source text MUST be read in full; cards MUST NOT serve as the basis for a revision.

Runtime Cards are compiled artifacts shipped under `kernel/Cards` and must not be hand-edited. The kernel owns the continuous R01-R13 route set, every Runtime Card, and their synchronization contract. A profile may add only a namespaced supplemental route, Read Set, or gate through its `Routing And Gate Registry`, using `P:<profile_id>:<route_name>` rather than the Rxx namespace; it cannot replace, shadow, or disable a kernel route or Runtime Card. When a Card conflicts with the Standards source text, the source text prevails, and regeneration is triggered per the Revision Write-back Checklist of [[kernel/K00 Standards Control/03 Standards Governance|Standards Governance]].

## Default Read Sets

Current Read Sets:

- [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]]: the shared control boundary for all tasks.
- [[kernel/Read Sets/R02 Single Note Authoring Read Set|Single Note Authoring]]: a single canonical note.
- [[kernel/Read Sets/R03 Module Build Read Set|Module Build]]: a complete knowledge module.
- [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]]: external sources and community signals.
- [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]]: creation, migration, and review of expression artifacts; the selected profile supplies the concrete artifact binding and may add supplemental gates.
- [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]]: moves, renames, splits, and directory restructuring.
- [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]]: batch, checkpoint, resume, and Terminal Proof.
- [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]]: task completion acceptance and Terminal Audit.
- [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]]: control-plane rule or structure changes.
- [[kernel/Read Sets/R10 Maintenance Run Read Set|Maintenance Run]]: periodic updates and freshness, digesting overdue re-review, watermark deltas, and needs_rereview within the budget envelope.
- [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]]: the canonical Large-scale Pre-execution Gate.
- [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]]: bounded review of changed, invalidated, overdue, sampled, or specialized-invariant scope.
- [[kernel/Read Sets/R13 Corpus Planning Read Set|Corpus Planning]]: maintain corpus topology, capability coverage, and semantic-gap admission without taking over content work, Queue execution, or audit.
