## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Next: [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].

## Purpose

Active Standards define the content, structure, citation, source, expression-layer split, and quality acceptance rules for the selected `knowledge-host` corpus.

The goal of these Standards is not to increase file count, but to ensure the knowledge corpus can support:

- Systematic learning: knowing prerequisites, core mechanisms, and follow-on directions.
- Deep understanding: able to explain reasons, assumptions, boundaries, and failure modes.
- Engineering practice: able to discuss implementation, evaluation, reliability, safety, and cost.
- Long-term maintenance: one concept has a single source of truth, and content can be reused and updated.
- Continuous evolution: able to discover knowledge gaps from official articles, papers, cases, and community signals, and to safely extend the knowledge graph through evidence synthesis.

## Operating Role

[[kernel/00 Standards Overview|00 Standards Overview]] is the sole entry point and rule router for the entire Standards system. It is responsible for telling the executor:

- Which Standards the current task MUST read.
- The order in which to read the Standards.
- Which constraints are always in effect.
- When modification of the knowledge corpus MAY begin.
- Which acceptance checks MUST be passed before completion.

The overall Index does not replace the detailed rules. A long-running task MUST NOT read only `00` and then execute directly; it MUST load the corresponding kernel Runtime Cards, with Read Sets and leaf modules read back in exception cases.

## Mandatory Reading Protocol

Before any knowledge-corpus task starts, resolve rules in the following order:

```text
00 Standards Overview
 -> Open The Kernel Card Index And Load Task Runtime Cards
 -> Escalate To Read Sets And Leaf Modules When Required
 -> Inspect Existing Knowledge And Links
 -> Freeze Task Contract And Loaded Set
 -> Execute One Verifiable Batch
 -> Gate Checks And Scripts
```

All tasks enter through the kernel-owned [[kernel/Cards/00 Card Index|Card Index]], then load [[kernel/Cards/01 Core Bootstrap Card|Core Bootstrap]] and the Runtime Card corresponding to the task. When the source text needs to be read back, select the Read Set corresponding to the actual task from [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]; a task being a knowledge-corpus long-running task MUST NOT by itself cause automatic loading of all modules of `01`, `02`, `08`, and `12`.

A long-running task MUST combine the Card corresponding to the actual content type with [[kernel/Cards/07 Long-running Execution Card|Long-running Execution]]; when reading back the source text, combine the corresponding Read Sets. Quality rules enter the contract at task start via the Gate list; the full gate procedure is read only when the corresponding checkpoint is reached.

The Task Contract or Progress Ledger MUST record:

- `standards_version`.
- The actual loaded set: kernel Runtime Card IDs and paths, any profile extension route explicitly combined with them, and module paths read back on escalation.
- The Runtime Cards and Read Sets used.
- Gate modules registered but not yet triggered.
- Re-resolution results after Standards or task scope changes.

## Card-first Reading Mode

The default reading mode is to read the task's kernel Runtime Card. A Card is a faithful compression of the corresponding Read Set's Start/Triggered/Gate modules, covering the determinations, procedures, and Gate lists needed for routine tasks.

In the following cases the Standards source text MUST be read back; cards alone MUST NOT be relied on:

- The card does not cover the current situation, or the card content is in doubt.
- A rule dispute or rule conflict requires adjudication.
- Depth rules for L-tier pages (the complete list is maintained only in the source text).
- Governance tasks: the RS 09 source text MUST be read in full; cards MUST NOT serve as the basis for a revision.

Runtime Cards are compiled artifacts shipped under `kernel/Cards` and must not be hand-edited. The kernel owns their required IDs, routes, and synchronization contract. A profile may add a domain-specific route or supplemental card through its `Routing And Gate Registry`, but it cannot replace, shadow, or disable a kernel card. When a card conflicts with the Standards source text, the source text prevails, and regeneration is triggered per the Revision Write-back Checklist of [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].

## Default Read Sets

Current Read Sets:

- [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]]: the shared control boundary for all tasks.
- [[kernel/Read Sets/02 Single Note Authoring Read Set|Single Note Authoring]]: a single canonical note.
- [[kernel/Read Sets/03 Module Build Read Set|Module Build]]: a complete knowledge module.
- [[kernel/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]]: external sources and community signals.
- The `Expression Layer Read Set` registered in the selected profile's `Routing And Gate Registry`: creation, migration, and review of expression-layer content.
- [[kernel/Read Sets/06 Migration and Refactor Read Set|Migration and Refactor]]: moves, renames, splits, and directory restructuring.
- [[kernel/Read Sets/07 Long-running Execution Read Set|Long-running Execution]]: batch, checkpoint, resume, and Terminal Proof.
- [[kernel/Read Sets/08 Audit and Completion Read Set|Audit and Completion]]: quality review and completion acceptance.
- [[kernel/Read Sets/09 Standards Governance Read Set|Standards Governance]]: control-plane rule or structure changes.
- [[kernel/Read Sets/10 Maintenance Run Read Set|Maintenance Run]]: periodic updates and freshness, digesting overdue re-review, watermark deltas, and needs_rereview within the budget envelope.
