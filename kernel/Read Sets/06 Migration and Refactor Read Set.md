## Purpose

Used for bulk moving, renaming, splitting, merging, or restructuring directories, while protecting user modifications, canonical ownership, incoming links, and recovery boundaries.

## Start

First read [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/02 Build Execution/01 Contract Time and Task State|Contract Time and Task State]]
- [[kernel/02 Build Execution/03 Inventory and Coverage Reconciliation|Inventory and Coverage Reconciliation]]
- [[kernel/02 Build Execution/06 Existing Changes Migration and Resume|Existing Changes Migration and Resume]]
- [[kernel/01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]]
- [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]]
- [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- [[kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns|Verification and Anti-patterns]]

Before migration, a manifest of source paths, target paths, incoming links, heading anchors, content owners, and the rollback boundary MUST be established. Migration batches MUST run in exclusive execution, not concurrently with other batches ([[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|02/05]] Concurrent Batches).

## Triggered

- Multi-batch migration: combine [[kernel/Read Sets/07 Long-running Execution Read Set|Long-running Execution]].
- Content owners change at the same time: read [[kernel/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].
- The Standards themselves change: combine [[kernel/Read Sets/09 Standards Governance Read Set|Standards Governance]].

## Gate

- [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]
- [[kernel/12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- [[kernel/12 Quality Assurance/06 Completion Terminal Audit and Final Report|Completion Terminal Audit and Final Report]]

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/02 Knowledge Base Build Execution Standard|Build Execution]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation]]
