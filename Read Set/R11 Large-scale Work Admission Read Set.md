---
type: read-set
schema_version: 1
route_id: R11
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R11:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
      - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
      - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
      - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
      - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
      - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
      - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
      - kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics.md
      - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
      - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
    read_sets:
      - R01
  - edge_id: R11:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R11:work-shape
    targets:
      - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
    read_sets:
      - R03
      - R04
      - R05
      - R06
      - R07
      - R13
  - edge_id: R11:admission
    kind: required
    phase_id: batch-preflight
    trigger_id: large-scale-admission-requested
    targets:
      - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
    read_sets: []
---
# R11 Large-scale Work Admission Read Set

## Purpose

Loads the planning and admission owners for large-scale creation, movement, or
deletion. It does not select or replace the route that performs the work.

## Non-deterministic triggers

- `R11:work-shape` fires when the admitted work actually has one of the listed
  module, source, expression, migration, long-running, planning, or visual
  shapes.
- `large-scale-admission-requested` fires before execution admission is sought.
