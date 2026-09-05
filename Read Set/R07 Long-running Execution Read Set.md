---
type: read-set
schema_version: 1
route_id: R07
activation_phase: batch-preflight
narrowable: true
load_edges:
  - edge_id: R07:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Control/07 Effort Tiering and Priority Quota.md
      - kernel/K00 Standards Control/09 Default Constraints Snapshot.md
      - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
      - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
      - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
      - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
      - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
      - kernel/K12 Quality Assurance/19 Incremental Audit Planning.md
      - kernel/K12 Quality Assurance/audit-plan-contract.yaml
      - kernel/K12 Quality Assurance/batch-close-closed-list.yaml
      - kernel/K12 Quality Assurance/batch-review-obligation-registry.yaml
      - kernel/K12 Quality Assurance/changed-scope-check-registry.yaml
      - kernel/K12 Quality Assurance/deterministic-rendering-contract.yaml
      - kernel/K12 Quality Assurance/profile-rendering-contract.yaml
      - kernel/K12 Quality Assurance/rendering-verification-contract.yaml
      - kernel/K12 Quality Assurance/substantive-review-contract.yaml
      - kernel/K13 Task Runtime and Execution Control/01 Runtime State Model and Namespace.md
      - kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics.md
      - kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules.md
      - kernel/K13 Task Runtime and Execution Control/07 Progress Ledger Contract.md
      - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
      - kernel/K13 Task Runtime and Execution Control/09 Queue Compilation Replanning and Views.md
      - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
      - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
      - kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery.md
      - kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate.md
    read_sets:
      - R01
      - R11
  - edge_id: R07:conditional
    kind: read-back
    phase_id: batch-running
    trigger_id: R07:runtime-event
    targets:
      - kernel/K06 Knowledge Intake and Evolution/02 User Guidance Hypotheses and Source Leads.md
      - kernel/K06 Knowledge Intake and Evolution/05 Evidence Maturity and Batch Policy.md
      - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
      - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
      - kernel/K12 Quality Assurance/04 Guidance and Source Review.md
      - kernel/K12 Quality Assurance/10 Standards Version Adoption.md
      - kernel/K12 Quality Assurance/17 Gate Receipt Payload Contract.md
      - kernel/K13 Task Runtime and Execution Control/04 Guidance Classification and Impact Analysis.md
      - kernel/K13 Task Runtime and Execution Control/05 Guidance Disposition and Safe Switching.md
      - kernel/K13 Task Runtime and Execution Control/06 Amendment Log and Controlled Replanning.md
      - kernel/K13 Task Runtime and Execution Control/15 Standards Adoption State Transaction.md
      - kernel/K13 Task Runtime and Execution Control/16 Resume Next Action Vocabulary.md
      - kernel/K13 Task Runtime and Execution Control/17 Escalation Policy.md
      - kernel/K13 Task Runtime and Execution Control/18 Initial Task Planning Transaction.md
    read_sets:
      - R13
  - edge_id: R07:gate
    kind: required
    phase_id: batch-gate
    trigger_id: batch-gate-requested
    targets:
      - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
      - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
      - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
      - kernel/K12 Quality Assurance/12 Substantive Correctness Review.md
      - kernel/K12 Quality Assurance/14 Batch Review.md
      - kernel/K12 Quality Assurance/audit-receipt-contract.yaml
      - kernel/K12 Quality Assurance/substantive-review-contract.yaml
      - kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings.md
    read_sets:
      - R08
---
# R07 Long-running Execution Read Set

## Purpose

Loads the common multi-batch, checkpoint, recovery, Queue, Progress, and delivery boundaries after R07 has already been selected.

## Non-deterministic triggers

- `R07:runtime-event` fires when a guidance change, replan, standards change, interruption, escalation, or planning reconciliation actually occurs.
- `batch-gate-requested` fires before the current batch seeks acceptance.
