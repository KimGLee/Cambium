---
type: read-set
schema_version: 1
route_id: R05
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R05:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
      - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
      - kernel/K08 Metadata and Status/03 Status Axes.md
      - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
      - kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links.md
      - kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links.md
      - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
      - kernel/K11 Expression Layer/01 Expression Architecture and Separation.md
      - kernel/K11 Expression Layer/02 Expression Coverage and Readiness.md
      - kernel/K11 Expression Layer/04 Evidence-bound Expression.md
      - kernel/K11 Expression Layer/05 Expression Knowledge Binding.md
    read_sets:
      - R01
  - edge_id: R05:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R05:artifact-condition
    targets:
      - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
      - kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md
      - kernel/K12 Quality Assurance/02 Rendering Verification.md
      - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
      - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
      - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
    read_sets:
      - R02
      - R03
      - R04
      - R06
      - R07
      - R08
      - R11
      - R12
  - edge_id: R05:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
      - kernel/K11 Expression Layer/01 Expression Architecture and Separation.md
      - kernel/K11 Expression Layer/07 Expression Migration Audit and Acceptance.md
      - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
      - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
    read_sets: []
---
# R05 Expression Layer Read Set

## Purpose

Loads the canonical-expression separation, binding, readiness, evidence, and acceptance owners for an already selected expression-layer route.

## Non-deterministic triggers

- `R05:artifact-condition` fires when the registered artifact actually needs another work route, migration, rendering, visual judgment, or evidence reuse.
- `batch-gate-requested` fires before expression-layer acceptance is requested.
