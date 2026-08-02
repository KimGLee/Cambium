## Purpose

Used for periodic knowledge base updates and freshness (Maintenance Run): within the declared budget envelope, absorb the `check_freshness` overdue list, watermark increments, `needs_rereview` propagation marks, and the candidates pool, and close the run with bounded Maintenance completion semantics.

## Start

First read [[kernel/Read Sets/01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] (Freshness And Review Due)
- [[kernel/06 Knowledge Intake and Evolution/03 Source-to-Knowledge Pipeline|Source-to-Knowledge Pipeline]] (Stage 1's incremental scan and watermark semantics)
- [[kernel/02 Build Execution/05 Batch Execution and Progress Ledger|Batch Execution and Progress Ledger]]
- [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]]

Before starting, the budget envelope MUST be declared (N pages, N batches, or N hours — choose one of the three), and the candidate manifest merged from four sources: overdue re-verification list ∪ watermark increment ∪ `needs_rereview` marks ∪ candidates pool (duplicate / vocab / language). A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only, and re-enters the pool when hit again by a new scan; at the start of a maintenance run, output the deferred age distribution, and items lingering more than 3 runs MUST be explicitly dispositioned. The owner of the rules above is [[kernel/00 Standards Control/08 Maintenance Run Envelope|00/08]]; this is an execution summary.

## Triggered

- `needs_rereview` items received: read [[kernel/12 Quality Assurance/11 Content-level Propagation#Content-level Propagation|Content-level Propagation]].
- Retirement or merge candidates appear: read [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].
- This run produces L-tier pages: read [[kernel/12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]].
- Source-driven content involved: combine [[kernel/Read Sets/04 Source-driven Expansion Read Set|Source-driven Expansion]].
- Expression Layer content involved: combine the `Expression Layer Read Set` registered by the selected profile through the `Routing And Gate Registry`.

## Gate

- Batch close: [[kernel/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]], then [[kernel/12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]] at serial merge.
- Closing this run's manifest: [[kernel/00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]] — bounded completion semantics: the run is complete when the candidate manifest within the envelope is closed + the Ledger and watermark are advanced + each batch passes the applicable QA gates; the vault-wide Terminal Proof does not apply, and deferred items cut off by the envelope hand over to the next maintenance run and do not constitute a gap.

## Related

- [[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution]]
- [[kernel/12 Quality Assurance Standard|Quality Assurance]]
