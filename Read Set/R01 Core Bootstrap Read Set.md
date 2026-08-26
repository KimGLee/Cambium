---
type: read-set
schema_version: 1
route_id: R01
activation_phase: batch-preflight
narrowable: false
load_edges:
  - edge_id: R01:start
    kind: required
    phase_id: batch-preflight
    trigger_id: route-selected
    targets:
      - kernel/K00 Standards Overview.md
      - kernel/K00 Standards Control/02 Task Routing.md
      - kernel/K00 Standards Control/03 Standards Governance.md
      - kernel/K00 Standards Control/04 Control State and Scope.md
      - kernel/K00 Standards Control/05 Core Principles.md
      - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
      - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
      - kernel/K00 Standards Control/17 Profile Dependency Closure.md
      - kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery.md
      - kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate.md
    read_sets: []
---
# R01 Core Bootstrap Read Set

## Purpose

Loads the common control boundary after R01 has already been selected. It does
not select another work route and does not authorize content work by itself.

## Non-deterministic triggers

This Read Set has no conditional read-back edge. Questions that exceed the
common boundary must be handled by the already selected work route.
