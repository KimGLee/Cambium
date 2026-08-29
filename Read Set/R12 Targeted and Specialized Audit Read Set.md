---
type: read-set
schema_version: 1
route_id: R12
activation_phase: batch-gate
narrowable: true
load_edges:
  - edge_id: R12:start
    kind: required
    phase_id: batch-gate
    trigger_id: route-selected
    targets:
      - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
      - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
      - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
      - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
      - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
      - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
      - kernel/K12 Quality Assurance/audit-plan-contract.yaml
      - kernel/K12 Quality Assurance/audit-receipt-contract.yaml
      - kernel/K12 Quality Assurance/batch-close-closed-list.yaml
      - kernel/K12 Quality Assurance/batch-review-obligation-registry.yaml
      - kernel/K12 Quality Assurance/changed-scope-check-registry.yaml
      - kernel/K12 Quality Assurance/deterministic-rendering-contract.yaml
      - kernel/K12 Quality Assurance/rendering-verification-contract.yaml
      - kernel/K12 Quality Assurance/substantive-review-contract.yaml
    read_sets:
      - R01
  - edge_id: R12:conditional
    kind: read-back
    phase_id: batch-gate
    trigger_id: R12:audit-scope
    targets:
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
      - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
      - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
      - kernel/K12 Quality Assurance/02 Rendering Verification.md
      - kernel/K12 Quality Assurance/04 Guidance and Source Review.md
      - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
    read_sets:
      - R05
      - R06
      - R08
      - R13
---
# R12 Targeted and Specialized Audit Read Set

## Purpose

Loads the shared targeted-audit boundary after R12 and its audit scope have already been selected. It does not decide the audit predicate or verdict.

## Non-deterministic triggers

`R12:audit-scope` fires only for the source, rendering, planning, expression, migration, completion, or planning-write-back dimensions actually implicated by the declared audit object.
