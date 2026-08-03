---
type: card-index
card_id: kernel-00
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/00 Read Sets Index.md
  - kernel/00 Standards Control/01 Operating Role and Reading Protocol.md
  - kernel/00 Standards Control/02 Task Routing and Pre-execution.md
source_hash: 9c21e576cfb3
card_registry:
  - card_id: kernel-01
    path: kernel/Cards/01 Core Bootstrap Card.md
    read_set: kernel/Read Sets/01 Core Bootstrap Read Set.md
  - card_id: kernel-02
    path: kernel/Cards/02 Single Note Authoring Card.md
    read_set: kernel/Read Sets/02 Single Note Authoring Read Set.md
  - card_id: kernel-03
    path: kernel/Cards/03 Module Build Card.md
    read_set: kernel/Read Sets/03 Module Build Read Set.md
  - card_id: kernel-04
    path: kernel/Cards/04 Source-driven Expansion Card.md
    read_set: kernel/Read Sets/04 Source-driven Expansion Read Set.md
  - card_id: kernel-06
    path: kernel/Cards/06 Migration and Refactor Card.md
    read_set: kernel/Read Sets/06 Migration and Refactor Read Set.md
  - card_id: kernel-07
    path: kernel/Cards/07 Long-running Execution Card.md
    read_set: kernel/Read Sets/07 Long-running Execution Read Set.md
  - card_id: kernel-08
    path: kernel/Cards/08 Audit and Completion Card.md
    read_set: kernel/Read Sets/08 Audit and Completion Read Set.md
  - card_id: kernel-09
    path: kernel/Cards/09 Standards Governance Card.md
    read_set: kernel/Read Sets/09 Standards Governance Read Set.md
  - card_id: kernel-10
    path: kernel/Cards/10 Maintenance Run Card.md
    read_set: kernel/Read Sets/10 Maintenance Run Read Set.md
---
# Card Index

## Kernel Ownership

This is the mandatory entry point to the kernel Runtime Card layer. Kernel Cards are read-only compiled guidance: they accelerate routine loading but never own rule text. Every selected profile uses this same layer. A profile may add a domain route or supplemental card through its `Routing And Gate Registry`, but it cannot replace, shadow, or disable a kernel Card.

## Card Registry

| Card ID | Routine task | Runtime Card | Canonical Read Set |
|---|---|---|---|
| `kernel-01` | Common control boundary for every task | [[kernel/Cards/01 Core Bootstrap Card\|Core Bootstrap]] | [[kernel/Read Sets/01 Core Bootstrap Read Set\|RS 01]] |
| `kernel-02` | Create or expand one canonical note | [[kernel/Cards/02 Single Note Authoring Card\|Single Note Authoring]] | [[kernel/Read Sets/02 Single Note Authoring Read Set\|RS 02]] |
| `kernel-03` | Build or expand a complete module | [[kernel/Cards/03 Module Build Card\|Module Build]] | [[kernel/Read Sets/03 Module Build Read Set\|RS 03]] |
| `kernel-04` | Turn sources into traceable corpus updates | [[kernel/Cards/04 Source-driven Expansion Card\|Source-driven Expansion]] | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|RS 04]] |
| `kernel-06` | Move, rename, split, merge, or restructure | [[kernel/Cards/06 Migration and Refactor Card\|Migration and Refactor]] | [[kernel/Read Sets/06 Migration and Refactor Read Set\|RS 06]] |
| `kernel-07` | Run a multi-batch task, checkpoint, or resume | [[kernel/Cards/07 Long-running Execution Card\|Long-running Execution]] | [[kernel/Read Sets/07 Long-running Execution Read Set\|RS 07]] |
| `kernel-08` | Review, close, or prove completion | [[kernel/Cards/08 Audit and Completion Card\|Audit and Completion]] | [[kernel/Read Sets/08 Audit and Completion Read Set\|RS 08]] |
| `kernel-09` | Modify the Standards or control plane | [[kernel/Cards/09 Standards Governance Card\|Standards Governance]] | [[kernel/Read Sets/09 Standards Governance Read Set\|RS 09]] |
| `kernel-10` | Run bounded freshness and maintenance work | [[kernel/Cards/10 Maintenance Run Card\|Maintenance Run]] | [[kernel/Read Sets/10 Maintenance Run Read Set\|RS 10]] |

## Loading Rules

1. Every task loads `kernel-01` plus one or more task Cards from the registry.
2. A long-running task additionally loads `kernel-07`.
3. A completion candidate additionally loads `kernel-08`.
4. A governance task loads `kernel-09`, then reads RS 09 and its Start modules in full; the Card is navigation only.
5. An expression-layer task additionally loads the route registered by the selected profile. No generic expression Card is implied when the profile registers none.
6. Record the Card IDs and paths actually loaded. Record Read Sets and leaf modules only when they are read back.

## Mandatory Source Read-back

Read the canonical Read Set and leaf owner rather than relying on a Card alone when the Card does not cover the situation, a rule is disputed, L-tier depth rules apply, or a governance change is being decided. On conflict, source text wins and the affected Card enters governance write-back.

## Integrity

`Tools/stamp_cards.py . --check` verifies Card membership, Read Set coverage, source boundaries, hashes, and version consistency. A missing or incomplete Card layer is a failure, not an optional profile state.
