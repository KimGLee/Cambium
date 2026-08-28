---
type: read-set
schema_version: 1
route_id: R06
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R06:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K01 Scope and Architecture/04 Folder and Shared Ownership.md
      - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
      - kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces.md
      - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
      - kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety.md
      - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
      - kernel/K08 Metadata and Status/05 Review Source and Migration Metadata.md
      - kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
      - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
      - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
    read_sets:
      - R01
  - edge_id: R06:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R06:affected-boundary
    targets:
      - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
      - kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md
      - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
    read_sets:
      - R07
      - R08
      - R09
      - R11
      - R12
      - R13
  - edge_id: R06:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
      - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
      - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
      - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
    read_sets: []
---
# R06 Migration and Refactor Read Set

## Purpose

Loads the ownership, path, structure, migration-safety, and acceptance owners for an already selected move, split, merge, rename, or refactor route.

## Non-deterministic triggers

- `R06:affected-boundary` fires when the migration reaches another canonical owner, relationship, expression, governance, planning, audit, or long-running boundary.
- `batch-gate-requested` fires before the migrated after-image is accepted.
