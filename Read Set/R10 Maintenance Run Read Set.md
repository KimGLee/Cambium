---
type: read-set
schema_version: 1
route_id: R10
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R10:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
      - kernel/K00 Standards Control/08 Maintenance Run Envelope.md
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production.md
      - kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
      - kernel/K08 Metadata and Status/05 Review Source and Migration Metadata.md
      - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
    read_sets:
      - R01
  - edge_id: R10:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R10:candidate-class
    targets:
      - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
      - kernel/K12 Quality Assurance/11 Content-level Propagation.md
      - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
      - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
    read_sets:
      - R04
      - R05
      - R07
      - R13
  - edge_id: R10:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
      - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
    read_sets: []
---
# R10 Maintenance Run Read Set

## Purpose

Loads the bounded maintenance envelope, freshness, migration metadata, and batch-review owners after R10 has already been selected.

## Non-deterministic triggers

- `R10:candidate-class` fires when an admitted maintenance candidate actually requires content, source, expression, planning, or long-running treatment.
- `batch-gate-requested` fires before the maintenance batch seeks acceptance.
