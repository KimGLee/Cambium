---
type: read-set
schema_version: 1
route_id: R08
activation_phase: task-completion
narrowable: false
load_edges:
  - edge_id: R08:completion
    kind: required
    phase_id: task-completion
    trigger_id: task-completion-requested
    targets:
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
      - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
      - kernel/K12 Quality Assurance/audit-receipt-contract.yaml
      - kernel/K12 Quality Assurance/08 Judgment Item Dimension Map.md
      - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
      - kernel/K12 Quality Assurance/15 Terminal Audit and Convergence.md
      - kernel/K12 Quality Assurance/16 Terminal Proof Contract.md
      - kernel/K12 Quality Assurance/18 Cross-page and Control-plane Dimension Map.md
      - kernel/K13 Task Runtime and Execution Control/11 Completion Policy.md
      - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
    read_sets:
      - R01
      - R12
---
# R08 Audit and Completion Read Set

## Purpose

Loads the terminal audit, evidence reconciliation, completion, and proof owners only after the completion phase has been requested.

## Non-deterministic triggers

`task-completion-requested` means the already selected task has entered its completion boundary. This Read Set does not decide that transition.
