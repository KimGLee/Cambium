---
type: runtime-card
route_id: R06
read_set: kernel/Read Sets/R06 Migration and Refactor Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R06 Migration and Refactor Read Set.md
  - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
  - kernel/K02 Knowledge Work Construction/10 Existing Changes and Migration Safety.md
  - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
  - kernel/K13 Task Runtime and Execution Control/14 Interruption Recovery and Rollover.md
  - kernel/K01 Scope and Architecture/04 Folder and Shared Ownership.md
  - kernel/K01 Scope and Architecture/05 Structural Unit Interface.md
  - kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces.md
  - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/K08 Metadata and Status/05 Review Source and Migration Metadata.md
  - kernel/K08 Metadata and Status/08 Relationship Metadata Contract.md
  - kernel/K09 Wiki Link and Navigation/03 Path Alias and Heading Links.md
  - kernel/K09 Wiki Link and Navigation/05 Verification and Anti-patterns.md
  - kernel/K10 Writing and Formatting/01 Naming Language and Prose.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K11 Expression Layer/06 Sequence and Progress Semantics.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
  - kernel/K12 Quality Assurance/09 Batch-close Closed List.md
  - kernel/K12 Quality Assurance/06 Completion Gate and Reporting.md
source_hash: '9c6cd466adec'
---
# R06 Migration and Refactor Card

> Compiled kernel guidance. Do not hand-edit. Complex conservation, ownership changes, and Standards migration require source read-back.

## Use When

Move, rename, split, merge, retire, or restructure files or directories. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]]. Pass R11 before large-scale creation, moves, or deletion. Migration batches execute exclusively in `serial-integrator` mode; combine R07 for multiple batches, R12 for a targeted or specialized migration audit, R13 when a bound planning artifact or mapped owner changes, and R09 when the Standards change.

## Before Start

- [ ] Freeze a migration manifest containing every source path, target path, incoming link, heading anchor, canonical owner, user modification, and rollback boundary.
- [ ] Reconcile the manifest with the file system and Coverage Ledger.
- [ ] Establish an explicit old-content-block → new-owner mapping; every original block has exactly one destination.
- [ ] Confirm that target ownership, naming, aliases, metadata, and profile language rules are valid before moving content.
- [ ] When the migration changes registered structure — unit roots, support-layer layouts, or a grouped taxonomy — freeze the target Structure Registry bindings and classification predicate before any file moves, and map every old path to its new class and directory in the manifest.
- [ ] When legacy relationship fields (`sources`, `source_note`, `source_notes`, `source_set`, `review_due`) are migrated, judge semantic equivalence per page and freeze an old-field to new-field manifest; names are never merged mechanically.
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
- [ ] The Coverage projection, Required Queue manifest, rollback record, and final file system agree.
- [ ] When the migration changed registered structure, close consumes a current `structure-registry` receipt from `python3 Tools/check_structure.py .` against the migrated snapshot.
- [ ] Coverage reconciliation does not read a sequence position, checkbox, file existence, resolvable link, or `Related` reference as authoring completion.

## Read Back When

Read R06 Read Set and the relevant owner for a split/merge dispute, heading compatibility, a simultaneous owner change, resume after interruption, multi-batch migration, or any destructive boundary. Large-scale admission reads R11; a whole-task completion candidate reads R08. Standards migration always reads R09 Read Set in full.
