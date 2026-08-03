## Purpose

A Read Set maps a task to the specific Standards modules that must be read. It solves the loading boundary; it does not replace any rule body.

Each kernel Read Set has a corresponding kernel-owned Runtime Card listed in [[kernel/Cards/00 Card Index|Card Index]]. Profiles cannot replace or disable these cards. This index and the Read Sets are used for exception read-back, L-tier depth rules, and Governance tasks; a profile may register an additional domain route through its `Routing And Gate Registry`, loaded alongside rather than instead of the kernel route.

## Resolution Order

```text
Open Standards Overview
 -> Load Core Bootstrap
 -> Classify Task
 -> Select One Or More Task Read Sets
 -> Resolve Triggered Modules
 -> Record Loaded Module Paths And Standards Version
 -> Execute
 -> Load Gate Modules At The Required Checkpoint
```

A task MAY combine multiple Read Sets. For example, expanding a system topic from primary sources while building expression layer artifacts requires combining Source-driven Expansion, Module Build, and the `Expression Layer Read Set` registered by the selected profile.

## Read Set Index

| Read Set | Use |
|---|---|
| [[kernel/Read Sets/01 Core Bootstrap Read Set\|Core Bootstrap]] | Common control constraints for all knowledge base tasks |
| [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring]] | Creating or targetedly expanding one canonical note |
| [[kernel/Read Sets/03 Module Build Read Set\|Module Build]] | Building a complete knowledge module including MOC, leaf pages, and cross-module relationships |
| [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion]] | Expanding knowledge from official documentation, papers, community signals, cases, or user source leads |
| `Expression Layer Read Set` | Creating, migrating, or reviewing expression layer artifacts registered by the selected profile |
| [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor]] | Bulk moving, renaming, splitting, merging, or restructuring directories |
| [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution]] | Long tasks requiring contract, batch, checkpoint, resume, and continuous state management |
| [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion]] | Performing quality review, the Completion Gate, and the Terminal Audit |
| [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance]] | Modifying Standards, Read Sets, rule versions, or control-plane structure |
| [[kernel/Read Sets/10 Maintenance Run Read Set\|Maintenance Run]] | Periodic knowledge base updates and freshness: absorbing overdue re-verification, watermark increments, and needs_rereview within the budget envelope |

## Selection Rules

- Every task starts from Core Bootstrap, but Core Bootstrap cannot replace task-specific rules.
- `Start` modules in a Read Set are read before the corresponding work starts.
- `Triggered` modules are loaded only when their trigger conditions appear.
- `Gate` modules are loaded before closing a note, batch, module, or task.
- A module's prerequisites take precedence over the current module; when a dependency cannot be satisfied, record the gap first.
- After the Standards version or module paths change, the affected loaded set MUST be re-resolved.
- The Task Contract or Progress Ledger SHOULD record the module paths actually read, not just a broad Standard number.

## Related

- [[kernel/00 Standards Overview|Standards Overview]]
- [[kernel/00 Standards Control/01 Operating Role and Reading Protocol|Operating Role and Reading Protocol]]
- [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]]
