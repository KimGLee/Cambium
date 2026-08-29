---
type: card
generation_mode: curated
route_id: R07
read_set_id: R07
read_set: Read Set/R07 Long-running Execution Read Set.md
source_files:
  - Read Set/R07 Long-running Execution Read Set.md
  - kernel/K12 Quality Assurance/02 Rendering Verification.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace.md
  - kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
  - kernel/K13 Task Runtime and Execution Control/17 Escalation Policy.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
source_hash: '945cfd207550'
reviewed_source_hash: '945cfd207550'
reviewed_card_hash: '872a0e9da739'
---
# R07 Long-running Execution Card

## Purpose

Execute admitted multi-batch work while keeping Queue, Progress, evidence, delivery, interruption, and handoff boundaries explicit.

## Actions

- Resume or reconcile the current runtime before selecting the next action.
- Confirm the frozen Standards/Profile identity and reconcile pending guidance before opening the next batch.
- Work only on an admitted batch whose dependencies and delivery gate are satisfied.
- Materialize the current AuditPlan, invoke the registered producer for every due obligation, and preserve each planned evidence kind; only `audit-receipt` obligations use the full AuditReceipt producer. Create the batch-review wrapper only after the complete due-stage closure resolves.
- Use the registered writer for every state transition, satisfy its required Gate evidence, and read back canonical state after each critical write.
- Require the applicable batch review and close Gates before accepting the batch result.
- Checkpoint accepted progress, evidence, remaining work, and the next safe action before yielding or handing off.

## Stop or escalate

- Stop on stale inputs, a failed Gate, conflicting state, uncertain write outcome, a structured `contract-gap` / HOLD for a selector-owned construct without a valid typed Profile Rendering Contract, or a recovery condition that has no proven next action.
- Escalate the registered runtime event instead of inventing a transition.

## Read-back hook

Resolve `R07:runtime-event` for guidance, replan, governance, interruption, escalation, or planning events; use the gate edge before batch acceptance.
