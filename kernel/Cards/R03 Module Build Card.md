---
type: runtime-card
route_id: R03
read_set: kernel/Read Sets/R03 Module Build Read Set.md
compiled_from: "{{standards_version}}"
source_files:
  - kernel/Read Sets/R03 Module Build Read Set.md
  - kernel/K01 Scope and Architecture/01 Scope Boundaries.md
  - kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine.md
  - kernel/K01 Scope and Architecture/03 Foundation Preservation.md
  - kernel/K01 Scope and Architecture/04 Folder and Shared Ownership.md
  - kernel/K02 Build Execution/03 Inventory and Coverage Reconciliation.md
  - kernel/K02 Build Execution/04 Architecture Samples and Dependency Build.md
  - kernel/K02 Build Execution/05 Batch Execution.md
  - kernel/K03 Note Types and Ownership/01 Note Type Catalog.md
  - kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes.md
  - kernel/K03 Note Types and Ownership/03 Split and Duplication Policy.md
  - kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links.md
  - kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation.md
  - kernel/K12 Quality Assurance/03 Module and Coverage Review.md
  - kernel/K12 Quality Assurance/14 Batch Review.md
  - kernel/K12 Quality Assurance/05 Automated and Manual Checks.md
source_hash: ff2fca1bde29
---
# R03 Module Build Card

> Compiled kernel guidance. Do not hand-edit. Placement disputes, full depth rules, and audit algorithms require source read-back.

## Use When

Build or systematically expand a complete module. Load [[kernel/Cards/R01 Core Bootstrap Card|Core Bootstrap]], the selected profile's `Profile Scope` and `Language Contract`, and [[kernel/Cards/R02 Single Note Authoring Card|Single Note Authoring]] for pages being authored.

## Before Start

- [ ] Freeze module scope, exclusions, logical architecture, knowledge spine, foundation boundary, and shared ownership.
- [ ] Inventory files and required knowledge objects; assign one canonical owner and one Coverage Ledger record to each in-scope object.
- [ ] Record missing prerequisites, gaps, incoming links, existing user modifications, and the dependency-ordered Required Queue.
- [ ] Choose representative samples for the relevant note types and validate them before bulk application.
- [ ] Split work into independently acceptable batches with disjoint manifests and resolved prerequisites.

## During

- Build dependency-ordered vertical slices while preserving independent foundation completeness.
- Do not duplicate a foundation inside a downstream page; link to its lowest reasonable shared owner.
- Keep note types, metadata, body links, Sources, MOC membership, and cross-module relationships synchronized.
- Follow canonical split and duplication conservation; file creation alone never satisfies a gap.
- Concurrent batches write only their own manifest, receipts, and delta. The integrator alone updates shared ledgers and hub pages during serial merge.
- Combine R04 for source intake, R05 for expression-layer work, R06 for moves or restructuring, and R07 for multi-batch execution. Load any namespaced profile route or gate only as a supplement to the applicable kernel route.

## Gate

- [ ] Every Required page reaches its target state and passes its tier-appropriate page gate.
- [ ] Ownership, Sources, metadata, body links, navigation, MOC coverage, and dependency order are synchronized.
- [ ] Batch in-scope checks, manual review, rendering evidence, AuditPlan, receipts, and delta are complete before `merge-ready`.
- [ ] The integrator applies each delta serially, runs the Batch-close Closed List, closes invalidations, and updates both Ledgers.
- [ ] Module review finds no unexplained prerequisite gap, duplicate owner, orphan, or false Overview claim.

Closing a complete module additionally loads [[kernel/Cards/R08 Audit and Completion Card|Audit and Completion]].

## Read Back When

Read the R03 Read Set and the relevant owners for placement disputes, shared-layer boundaries, split/merge judgment, batch concurrency, receipt handling, or full module acceptance. For expression artifacts, combine the R05 Read Set and the selected profile's concrete binding.
