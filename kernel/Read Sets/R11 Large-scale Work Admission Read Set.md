---
type: read-set
route_id: R11
---

## Purpose

Used only to admit large-scale creation, moves, or deletion to execution. It packages the existing Pre-execution Gate; it does not authorize authoring, source promotion, expression work, migration, or long-running execution by itself.

## Start

First load [[kernel/Read Sets/R01 Core Bootstrap Read Set|R01 Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/02 Task Routing and Pre-execution#Pre-execution Gate|Pre-execution Gate]]
- [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Task Contract Decisions|Task Contract Decisions]]
- [[kernel/K02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Incremental Audit Planning|Incremental Audit Planning]]

Also load the route for the actual work. R11 never replaces that route.

## Triggered

- Module construction: combine [[kernel/Read Sets/R03 Module Build Read Set|R03 Module Build]].
- Source-driven work: combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|R04 Source-driven Expansion]].
- Expression-layer work: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and its profile binding.
- Moves, splits, merges, or deletion: combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|R06 Migration and Refactor]].
- Multiple batches, checkpointing, or resume: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|R07 Long-running Execution]].
- A visual escalation proposal: read [[kernel/K12 Quality Assurance/13 Visual Verification Escalation|Visual Verification Escalation]] before registering its objective trigger and unresolved question.

## Admission Gate

Every item in the canonical [[kernel/K00 Standards Control/02 Task Routing and Pre-execution#Pre-execution Gate|Pre-execution Gate]] MUST be resolved. At task start only the Audit Receipt Register is loaded; an AuditPlan is built exactly once before batch close. When any admission condition is missing, remain in planning or investigation.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Base Build Execution Standard|Build Execution]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
