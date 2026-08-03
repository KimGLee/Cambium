---
type: runtime-card
card_id: kernel-06
read_set: kernel/Read Sets/06 Migration and Refactor Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/06 Migration and Refactor Read Set.md
  - kernel/02 Build Execution/01 Contract Time and Task State.md
  - kernel/02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - kernel/02 Build Execution/05 Batch Execution.md
  - kernel/02 Build Execution/06 Existing Changes Migration and Resume.md
  - kernel/01 Scope and Architecture/04 Folder and Shared Ownership.md
  - kernel/03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/08 Metadata and Status/05 Review Source and Migration Metadata.md
  - kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - kernel/09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - kernel/12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/12 Quality Assurance/14 Batch Review.md
  - kernel/12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: a18f00f10043
---
# Migration and Refactor Card

> Compiled kernel guidance. Do not hand-edit. Complex conservation, ownership changes, and Standards migration require source read-back.

## Use When

Move, rename, split, merge, retire, or restructure files or directories. Load [[kernel/Cards/01 Core Bootstrap Card|Core Bootstrap]]. Migration batches execute exclusively; combine `kernel-07` for multiple batches and `kernel-09` when the Standards change.

## Before Start

- [ ] Freeze a migration manifest containing every source path, target path, incoming link, heading anchor, canonical owner, user modification, and rollback boundary.
- [ ] Reconcile the manifest with the file system and Coverage Ledger.
- [ ] Establish an explicit old-content-block → new-owner mapping; every original block has exactly one destination.
- [ ] Confirm that target ownership, naming, aliases, metadata, and profile language rules are valid before moving content.
- [ ] Isolate the migration batch from concurrent content batches.

## During

Use the safe order: create and verify the target → update references and heading links → reconcile content conservation and ownership → verify links and navigation → only then remove the superseded object when deletion is authorized.

- Existing changes of uncertain origin belong to the user; preserve rather than reset them.
- Never delete first, use destructive reset as migration, or hide a rule/content loss inside a split.
- Preserve unique content and Sources; do not create duplicate canonical owners.
- Synchronize aliases, metadata, incoming links, MOCs, and replacement/tombstone state.
- Record a checkpoint with modified paths and the next exact action before pausing.

## Gate

- [ ] Old-block → new-owner reconciliation is complete with no omission or duplicate owner.
- [ ] New targets are complete and reachable before old paths are retired or deleted.
- [ ] Missing, ambiguous, path, alias, and heading links are resolved.
- [ ] Module/Coverage Review, Batch Review, applicable deterministic checks, and the Batch-close Closed List pass on the merged snapshot.
- [ ] The Coverage Ledger and rollback record match the final file system.

## Read Back When

Read RS 06 and the relevant owner for a split/merge dispute, heading compatibility, a simultaneous owner change, resume after interruption, multi-batch migration, or any destructive boundary. Standards migration always reads RS 09 in full.
