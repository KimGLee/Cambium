---
type: read-set
route_id: R06
---

## Purpose

Used for moving, renaming, splitting, merging, or restructuring files or directories, while protecting user modifications, canonical ownership, incoming links, and recovery boundaries.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[kernel/K02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]]
- [[kernel/K01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]
- [[kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]]

Before migration, a manifest of source paths, target paths, incoming links, heading anchors, content owners, and the rollback boundary MUST be established. Migration batches MUST run in exclusive execution, not concurrently with other batches ([[kernel/K02 Build Execution/05 Batch Execution|K02/05]] Concurrent Batches).

## Triggered

- Large-scale creation, moves, or deletion: pass [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]] before execution.
- Multi-batch migration: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]].
- Content owners change at the same time: read [[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].
- The Standards themselves change: combine [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]].
- A targeted or specialized migration audit: combine [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]].
- A whole-task completion candidate: combine [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]].

## Gate

- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]], run by the integrator on the batch in which the migration closes
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Base Build Execution Standard|Build Execution]]
- [[kernel/K09 Wiki Link and Navigation Standard|Wiki Link and Navigation]]
