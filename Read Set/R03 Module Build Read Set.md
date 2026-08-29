---
type: read-set
schema_version: 1
route_id: R03
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R03:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
      - kernel/K01 Scope and Architecture/01 Scope Boundaries.md
      - kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine.md
      - kernel/K01 Scope and Architecture/03 Foundation Preservation.md
      - kernel/K01 Scope and Architecture/04 Folder and Shared Ownership.md
      - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
      - kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces.md
      - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
      - kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation.md
      - kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning.md
      - kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production.md
      - kernel/K03 Note Types and Ownership/01 Note Type Catalog.md
      - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
      - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
      - kernel/K04 Content Depth/01 Depth Model and Foundation.md
      - kernel/K04 Content Depth/02 Core Concept Structure.md
      - kernel/K04 Content Depth/03 Process and Flow Structure.md
      - kernel/K04 Content Depth/04 System and Production Reasoning.md
      - kernel/K04 Content Depth/05 Source and Evaluation Depth.md
      - kernel/K04 Content Depth/06 Examples Deep Dives and Failure Analysis.md
      - kernel/K08 Metadata and Status/03 Status Axes.md
      - kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links.md
      - kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation.md
      - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
    read_sets:
      - R01
  - edge_id: R03:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R03:related-work
    targets:
      - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
      - kernel/K12 Quality Assurance/11 Content-level Propagation.md
    read_sets:
      - R02
      - R04
      - R05
      - R06
      - R07
      - R11
      - R13
  - edge_id: R03:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
      - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
      - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
    read_sets:
      - R08
      - R12
---
# R03 Module Build Read Set

## Purpose

Loads the architecture, ownership, coverage, depth, and module-review owners for an already selected module-build route.

## Non-deterministic triggers

- `R03:related-work` fires only when the module work actually includes the corresponding authoring, source, expression, migration, long-running, admission, or planning concern.
- `batch-gate-requested` fires before module or batch acceptance is requested.
