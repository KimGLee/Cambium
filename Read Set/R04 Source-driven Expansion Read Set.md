---
type: read-set
schema_version: 1
route_id: R04
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R04:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
      - kernel/K06 Knowledge Intake and Evolution/01 Intake Scope and Knowledge Model.md
      - kernel/K06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline.md
      - kernel/K06 Knowledge Intake and Evolution/04 Intake Note Types and Source Roles.md
      - kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy.md
      - kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark.md
      - kernel/K06 Knowledge Intake and Evolution/08 Canonical Promotion Gate.md
      - kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles.md
      - kernel/K07 Sources and Accuracy/02 Claims Sources and Classification.md
      - kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification.md
      - kernel/K08 Metadata and Status/04 Evidence and Relationship Metadata.md
      - kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md
    read_sets:
      - R01
  - edge_id: R04:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R04:semantic-condition
    targets:
      - kernel/K05 Terminology/01 Terminology Extraction.md
      - kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads.md
      - kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality.md
      - kernel/K07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty.md
    read_sets:
      - R02
      - R07
      - R08
      - R11
      - R12
  - edge_id: R04:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K06 Knowledge Intake and Evolution/06 Intake Anti-patterns and Acceptance.md
      - kernel/K07 Sources and Accuracy/06 Source Maintenance and Acceptance.md
      - kernel/K12 Quality Assurance/04 Guidance and Source Review.md
    read_sets: []
---
# R04 Source-driven Expansion Read Set

## Purpose

Loads the intake, source-authority, evidence, and promotion owners for an
already selected source-driven route.

## Non-deterministic triggers

- `R04:semantic-condition` fires when terminology, source quality,
  uncertainty, another work route, or a broader execution boundary is actually
  implicated by the admitted source work.
- `batch-gate-requested` fires before source promotion or source-review
  acceptance is requested.
