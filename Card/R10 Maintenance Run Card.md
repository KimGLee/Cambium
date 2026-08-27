---
type: card
generation_mode: curated
route_id: R10
read_set_id: R10
read_set: Read Set/R10 Maintenance Run Read Set.md
source_files:
  - Read Set/R10 Maintenance Run Read Set.md
  - kernel/K00 Standards Control/08 Maintenance Run Envelope.md
  - kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
source_hash: '516f8915c5a3'
reviewed_source_hash: '516f8915c5a3'
reviewed_card_hash: 'c2e9f1f0bf63'
---
# R10 Maintenance Run Card

## Purpose

Process a bounded maintenance envelope without silently expanding it into an
unbounded rebuild or a different task type.

## Actions

- Freeze the maintenance envelope, candidate classes, budget, watermark, and
  affected scope before work begins.
- Submit each admitted candidate class to task routing and combine only the
  route returned for that class.
- Keep accepted dispositions, the Ledger, and the current watermark
  synchronized.
- Require the applicable batch Gate and registered maintenance completion Gate.

## Stop or escalate

- Stop at a batch boundary when the envelope or budget is exhausted; stop when
  the candidate leaves scope or a required route was not selected.
- Escalate a systemic finding that requires new scope, policy, or architecture.

## Read-back hook

Resolve `R10:candidate-class` for content, source, expression, planning, or
long-running candidates; use the gate edge before close.
