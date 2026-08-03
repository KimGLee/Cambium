---
type: read-set
route_id: R10
---

## Purpose

Used for periodic knowledge base updates and freshness (Maintenance Run): within the declared budget envelope, absorb the `check_freshness` overdue list, watermark increments, `needs_rereview` propagation marks, and the candidates pool, and close the run with bounded Maintenance completion semantics.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] (Freshness And Review Due)
- [[kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark|Environmental Scanning and Watermark]]
- [[kernel/K02 Build Execution/05 Batch Execution|Batch Execution]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]

Before starting, the budget envelope MUST be declared (N pages, N batches, or N hours — choose one of the three), and the candidate manifest merged from four sources: overdue re-verification list ∪ watermark increment ∪ `needs_rereview` marks ∪ candidates pool (duplicate / vocab / language). A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only, and re-enters the pool when hit again by a new scan; at the start of a maintenance run, output the deferred age distribution, and items lingering more than 3 runs MUST be explicitly dispositioned. The owner of the rules above is [[kernel/K00 Standards Control/08 Maintenance Run Envelope|K00/08]]; this is an execution summary.

For retirement of high-in-degree pages, convert incoming-link retargeting into the page budget at `retargeted links ÷ 6`, as fixed by K00/08.

## Triggered

- `needs_rereview` items received: read [[kernel/K12 Quality Assurance/11 Content-level Propagation#Content-level Propagation|Content-level Propagation]].
- Retirement or merge candidates appear: read [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].
- This run produces L-tier pages: read [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]].
- Source-driven content involved: combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]].
- Expression Layer content involved: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and the artifact's profile binding or supplemental gate.

## Gate

- Batch close: [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]], then [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]] at serial merge.
- Closing this run's manifest: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]] — bounded completion semantics: the run is complete when the candidate manifest within the envelope is closed + the Ledger and watermark are advanced + each batch passes the applicable QA gates; the vault-wide Terminal Proof does not apply, and deferred items cut off by the envelope hand over to the next maintenance run and do not constitute a gap.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
