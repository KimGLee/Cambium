---
type: read-set
route_id: R06
---

## Purpose

Used for moving, renaming, splitting, merging, or restructuring files or directories, while protecting user modifications, canonical ownership, incoming links, and recovery boundaries.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety|Existing Changes and Migration Safety]]
- [[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|Batch Admission Transitions and Serial Integration]]
- [[kernel/K01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]
- [[kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- [[kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]]

Before migration, a manifest of source paths, target paths, incoming links, heading anchors, content owners, and the rollback boundary MUST be established. Migration batches MUST run in exclusive execution, not concurrently with other batches ([[kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration|K13/10]] Concurrent Batches).

## Triggered

- Large-scale creation, moves, or deletion: pass [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]] before execution.
- Multi-batch migration: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]].
- Content owners change at the same time: read [[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].
- The Standards themselves change: combine [[kernel/Read Sets/R09 Standards Governance Read Set|Standards Governance]].
- A bound planning artifact or mapped canonical-owner path changes: combine [[kernel/Read Sets/R13 Corpus Planning Read Set|Corpus Planning]] so the Global Map, Capability Matrix, and Gap Register are reconciled after the migration.
- A targeted or specialized migration audit: combine [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]].
- A whole-task completion candidate: combine [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]].
- Coverage reconciliation meets a sequence position, checkbox, or other progress marker: read [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]], which [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] names as the owner of that status separation.

## Gate

- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]], run by the integrator on the batch in which the migration closes
- [[kernel/K12 Quality Assurance/06 Completion Gate and Reporting|Completion Gate and Reporting]]

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction]]
- [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control]]
- [[kernel/K09 Wiki Link and Navigation Standard|Wiki Link and Navigation]]
