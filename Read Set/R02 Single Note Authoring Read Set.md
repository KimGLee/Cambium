---
type: read-set
schema_version: 1
route_id: R02
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R02:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
      - kernel/K03 Note Types and Ownership/01 Note Type Catalog.md
      - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
      - kernel/K04 Content Depth/01 Depth Model and Foundation.md
      - kernel/K04 Content Depth/02 Core Concept Structure.md
      - kernel/K04 Content Depth/03 Process and Flow Structure.md
      - kernel/K04 Content Depth/04 System and Production Reasoning.md
      - kernel/K04 Content Depth/05 Source and Evaluation Depth.md
      - kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies.md
      - kernel/K08 Metadata and Status/02 Scope Level Depth and Priority.md
      - kernel/K08 Metadata and Status/03 Status Axes.md
      - kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract.md
      - kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority.md
      - kernel/K09 Wiki Link and Navigation/01 Link Semantics and Body Links.md
      - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
      - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
      - kernel/K12 Quality Assurance/audit-plan-contract.yaml
      - kernel/K12 Quality Assurance/batch-close-closed-list.yaml
      - kernel/K12 Quality Assurance/batch-review-obligation-registry.yaml
      - kernel/K12 Quality Assurance/changed-scope-check-registry.yaml
      - kernel/K12 Quality Assurance/deterministic-rendering-contract.yaml
      - kernel/K12 Quality Assurance/profile-rendering-contract.yaml
      - kernel/K12 Quality Assurance/rendering-verification-contract.yaml
      - kernel/K12 Quality Assurance/substantive-review-contract.yaml
    read_sets:
      - R01
  - edge_id: R02:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R02:semantic-condition
    targets:
      - kernel/K04 Content Depth/06 Examples Deep Dives and Failure Analysis.md
      - kernel/K05 Terminology/01 Terminology Extraction.md
      - kernel/K05 Terminology/02 Ownership and Term Structure.md
      - kernel/K05 Terminology/03 Naming Context and Linking.md
      - kernel/K05 Terminology/04 Terminology Acceptance.md
      - kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles.md
      - kernel/K07 Sources and Accuracy/02 Claims Sources and Classification.md
      - kernel/K07 Sources and Accuracy/03 Official and Cross-source Verification.md
      - kernel/K07 Sources and Accuracy/04 Evaluation and Source Quality.md
      - kernel/K07 Sources and Accuracy/05 Time Formula Terminology and Uncertainty.md
      - kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md
      - kernel/K08 Metadata and Status/09 Page Boundary Contract.md
      - kernel/K10 Writing and Formatting/02 Mathematics Tables and Code.md
      - kernel/K10 Writing and Formatting/03 Diagrams and Assets.md
      - kernel/K12 Quality Assurance/11 Content-level Propagation.md
    read_sets: []
  - edge_id: R02:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K10 Writing and Formatting/04 Rendering and Formatting Review.md
      - kernel/K12 Quality Assurance/01 Quality Dimensions and Single Note Review.md
      - kernel/K12 Quality Assurance/02 Rendering Verification.md
      - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
      - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
      - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
    read_sets: []
---
# R02 Single Note Authoring Read Set

## Purpose

Loads the canonical owners needed to create or change one knowledge page after R02 has already been selected.

## Non-deterministic triggers

- `R02:semantic-condition` fires when the page presents a terminology, evidence, relationship, propagation, diagram, code, or mathematical case that the start boundary does not settle.
- `batch-gate-requested` fires before the page participates in its applicable review boundary.
