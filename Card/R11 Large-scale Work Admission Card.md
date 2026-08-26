---
type: card
generation_mode: curated
route_id: R11
read_set_id: R11
read_set: Read Set/R11 Large-scale Work Admission Read Set.md
standards_version: '{{ standards_version }}'
source_files:
  - Read Set/R11 Large-scale Work Admission Read Set.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
  - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
source_hash: 'e44372da7b97'
reviewed_source_hash: 'e44372da7b97'
reviewed_card_hash: '3b3b42c122c4'
---
# R11 Large-scale Work Admission Card

## Purpose

Decide whether already scoped large-scale work is ready to enter execution;
R11 never replaces the route that performs the work.

## Actions

- Confirm the scope, affected objects, planning applicability, dependencies,
  execution units, and rollback or recovery boundary.
- Submit the actual work and any planning need to task routing before
  admission.
- Require `large-scale-execution-admission` before large-scale creation,
  movement, or deletion begins.
- Preserve the admitted plan and resulting readiness evidence for the runtime.

## Stop or escalate

- Remain in planning when the corpus plan, affected closure, Queue, Coverage,
  dependency, authority, or recovery condition is incomplete.
- Escalate a proposed scope or risk acceptance change for confirmation.

## Read-back hook

Resolve `R11:work-shape` for the actual module, source, expression, migration,
long-running, planning, or visual dimension before admission.
