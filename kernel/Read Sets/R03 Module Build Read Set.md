---
type: read-set
route_id: R03
---

## Purpose

Used for building or systematically expanding a complete knowledge module, including logical placement, canonical ownership, leaf pages, MOC, cross-module dependencies, and batch acceptance.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K01 Scope and Architecture/01 Scope Boundaries|Scope Boundaries]]
- [[kernel/K01 Scope and Architecture/02 Logical Architecture and Knowledge Spine|Logical Architecture and Knowledge Spine]]
- [[kernel/K01 Scope and Architecture/03 Foundation Preservation|Foundation Preservation]]
- [[kernel/K01 Scope and Architecture/04 Folder and Shared Ownership|Folder and Shared Ownership]]
- [[kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger|Inventory and Coverage Ledger]]
- [[kernel/K02 Knowledge Work Construction/02 Coverage Reconciliation|Coverage Reconciliation]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K02 Knowledge Work Construction/08 Architecture Samples and Dependency Planning|Architecture Samples and Dependency Planning]]
- [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production|Knowledge Batch Production]]
- [[kernel/K03 Note Types and Ownership/01 Note Type Catalog|Note Type Catalog]]
- [[kernel/K03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]]
- [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]
- [[kernel/K04 Content Depth/01 Depth Model and Foundation|Depth Model and Foundation]]
- By the page types in the module, load [[kernel/K04 Content Depth/02 Core Concept Structure|Core Concept Structure]], [[kernel/K04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]], [[kernel/K04 Content Depth/04 System and Production Reasoning|System and Production Reasoning]], or [[kernel/K04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]] respectively.
- When instances, deep dives, failure modes, or debugging are needed, load [[kernel/K04 Content Depth/06 Examples Deep Dives and Failure Analysis|Examples Deep Dives and Failure Analysis]].
- [[kernel/K08 Metadata and Status/03 Status Axes|Status Axes]]
- [[kernel/K09 Wiki Link and Navigation/02 Structural and Bidirectional Links|Structural and Bidirectional Links]]
- [[kernel/K09 Wiki Link and Navigation/04 MOC Related and Link Creation|MOC Related and Link Creation]]
- [[kernel/K10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]]
- The `Language Contract` registered by the selected profile, as a mandatory `Start` module of this Read Set.

## Triggered

- Authoring, rewriting, or targetedly completing any page of the module: combine [[kernel/Read Sets/R02 Single Note Authoring Read Set|Single Note Authoring]]. R03 owns placement, coverage, and batch acceptance; R02 owns the page's own `Start`, `Triggered`, and note gate modules.
- Source-driven expansion: combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]].
- Expression-layer work or synchronization: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and the artifact's profile binding or supplemental gate.
- Large-scale module work: pass [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|Large-scale Work Admission]] before execution.
- Long tasks and multiple batches: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|Long-running Execution]].
- Renaming or moving existing pages: combine [[kernel/Read Sets/R06 Migration and Refactor Read Set|Migration and Refactor]].
- Creating or reconciling a Global Map, Capability Matrix, or Gap Register, or promoting a module gap into Coverage: combine [[kernel/Read Sets/R13 Corpus Planning Read Set|Corpus Planning]]. R03 authors the module; R13 owns the planning artifacts and handoff.
- Mechanism sections of an existing page (Definition, Mechanism, formulas, core conclusions) are substantively modified: read [[kernel/K12 Quality Assurance/11 Content-level Propagation|Content-level Propagation]] and mark the direct downstream notes.
- Coverage reconciliation meets a sequence position, checkbox, or other progress marker: read [[kernel/K11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]], which [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]] names as the owner of that status separation.

## Gate

- [[kernel/K12 Quality Assurance/03 Module and Coverage Review|Module and Coverage Review]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]
- For a multi-batch module, consume the current `Tools/check_queue.py` receipt at activation and batch close; Queue validation remains owned by [[kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle|K13/08]].
- [[kernel/K12 Quality Assurance/05 Automated and Manual Checks|Automated and Manual Checks]]
- When the task is an independent targeted or specialized module audit, combine [[kernel/Read Sets/R12 Targeted and Specialized Audit Read Set|Targeted and Specialized Audit]].
- When the whole task enters `completion-candidate`, combine [[kernel/Read Sets/R08 Audit and Completion Read Set|Audit and Completion]].

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K01 Scope and Architecture Standard|Scope and Architecture]]
- [[kernel/K02 Knowledge Work Construction Standard|Knowledge Work Construction]]
- [[kernel/K13 Task Runtime and Execution Control Standard|Task Runtime and Execution Control]]
