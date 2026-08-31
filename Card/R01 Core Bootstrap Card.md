---
type: card
generation_mode: curated
route_id: R01
read_set_id: R01
read_set: Read Set/R01 Core Bootstrap Read Set.md
source_files:
  - Read Set/R01 Core Bootstrap Read Set.md
  - kernel/K00 Standards Control/02 Task Routing.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K13 Task Runtime and Execution Control/19 Card Context Activation and Read-back Delivery.md
  - kernel/K13 Task Runtime and Execution Control/20 Assignment State and Delivery Gate.md
source_hash: 'af627ccd6556'
reviewed_source_hash: 'af627ccd6556'
reviewed_card_hash: '1349cae9d74e'
---
# R01 Core Bootstrap Card

## Purpose

Establish the common preflight boundary after the task routes are already selected. R01 does not authorize the work performed by another route.

## Actions

- Require a current `profile-load` result for the selected Profile.
- Resolve the R01 Read Set and the already selected work-route Read Sets.
- Invoke `runtime-startup-recovery` before any state write; resume or reconcile an existing runtime instead of replacing it.
- Require `card-context-delivery-v1` and its delivery gate before acting from this Card.

## Stop or escalate

- Stop when the Profile, selected route, resolved load plan, or delivery evidence is missing or stale.
- Escalate when the requested action would change Standards or the selected Profile.

## Read-back hook

Return to Read Set `R01` for an unresolved startup, authority, recovery, or delivery question; the referenced canonical owner decides the result.
