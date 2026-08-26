---
type: read-set
schema_version: 1
route_id: R13
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R13:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine.md
      - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
      - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
      - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
    read_sets:
      - R01
  - edge_id: R13:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R13:planning-relation
    targets:
      - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
      - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
      - kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation.md
      - kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning.md
    read_sets:
      - R06
      - R12
---
# R13 Corpus Planning Read Set

## Purpose

Loads the corpus-planning object, structure, and reconciliation owners after
R13 has already been selected. It does not author corpus pages or run audits.

## Non-deterministic triggers

`R13:planning-relation` fires when the planning change actually touches a
structural unit, Coverage handoff, migration, architecture decision, or audit
scope.
