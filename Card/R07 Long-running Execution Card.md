---
type: card
generation_mode: curated
route_id: R07
read_set_id: R07
read_set: Read Set/R07 Long-running Execution Read Set.md
source_files:
  - Read Set/R07 Long-running Execution Read Set.md
  - kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace.md
  - kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
  - kernel/K13 Task Runtime and Execution Control/17 Escalation Policy.md
source_hash: 'cbb8ecd3902b'
reviewed_source_hash: 'cbb8ecd3902b'
reviewed_card_hash: '80c3e2c1d9f9'
---
# R07 Long-running Execution Card

## Purpose

Execute admitted multi-batch work while keeping Queue, Progress, evidence,
delivery, interruption, and handoff boundaries explicit.

## Actions

- Resume or reconcile the current runtime before selecting the next action.
- Confirm the frozen Standards/Profile identity and reconcile pending guidance
  before opening the next batch.
- Work only on an admitted batch whose dependencies and delivery gate are
  satisfied.
- Use the registered writer for every state transition, satisfy its required
  Gate evidence, and read back canonical state after each critical write.
- Require the applicable batch review and close Gates before accepting the
  batch result.
- Checkpoint accepted progress, evidence, remaining work, and the next safe
  action before yielding or handing off.

## Stop or escalate

- Stop on stale inputs, a failed Gate, conflicting state, uncertain write
  outcome, or a recovery condition that has no proven next action.
- Escalate the registered runtime event instead of inventing a transition.

## Read-back hook

Resolve `R07:runtime-event` for guidance, replan, governance, interruption,
escalation, or planning events; use the gate edge before batch acceptance.
