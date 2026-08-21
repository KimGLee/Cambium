---
type: read-set
route_id: R10
---

## Purpose

Used for periodic knowledge base updates and freshness (Maintenance Run): within the declared budget envelope, absorb the complete `check_freshness` candidate set, watermark increments, `needs_rereview` propagation marks, and the candidates pool, and close the run with bounded Maintenance completion semantics.

## Start

First read [[kernel/Read Sets/R01 Core Bootstrap Read Set|Core Bootstrap]], then read:

- [[kernel/K00 Standards Control/08 Maintenance Run Envelope|Maintenance Run Envelope]]
- [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|Effort Tiering and Priority Quota]]
- [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]] (Freshness And Review Due)
- [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|Frontmatter Writer and Projection Authority]] (derived freshness stays unpersisted; `source_valid_until` owns real external validity)
- [[kernel/K06 Knowledge Intake and Evolution/07 Environmental Scanning and Watermark|Environmental Scanning and Watermark]]
- [[kernel/K02 Knowledge Work Construction/09 Knowledge Batch Production|Knowledge Batch Production]]
- [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|Corpus Planning Runtime Audit and Gate Boundaries]]
- [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]]

Before starting, the budget envelope MUST be declared (N pages, N batches, or N hours — choose one of the three), and the candidate manifest merged from four sources: complete freshness candidate set ∪ watermark increment ∪ `needs_rereview` marks ∪ candidates pool (duplicate / vocab / language). Consume every freshness `candidate` outcome; do not filter the source back to overdue pages or treat an unresolved active page as absent. A candidate not selected by the budget for 3 consecutive maintenance runs is automatically demoted to log-only, and re-enters the pool when hit again by a new scan; at the start of a maintenance run, output the deferred age distribution, and items lingering more than 3 runs MUST be explicitly dispositioned. The owner of fusion, ordering, and deferral is [[kernel/K00 Standards Control/08 Maintenance Run Envelope|K00/08]]; freshness outcome semantics remain in [[kernel/K08 Metadata and Status/05 Review Source and Migration Metadata|K08/05]]. This Read Set is an execution summary.

Before any write, probe the adopting repository for `.cambium/state/`. If it
exists, resume its recorded task through `check_queue.py --resume-status`; do
not initialize or overwrite it. If task state is absent, initialize only when
this run is persistent, resumable, or multi-batch, preserving any canonical
governance/history already under `.cambium/`, and declare
`--completion-semantics maintenance`. A bounded single-note maintenance run
does not create an empty runtime namespace merely to use R10.

For retirement of high-in-degree pages, convert incoming-link retargeting into the page budget at `retargeted links ÷ 6`, as fixed by K00/08.

## Triggered

- `needs_rereview` items received: read [[kernel/K12 Quality Assurance/11 Content-level Propagation#Content-level Propagation|Content-level Propagation]].
- Retirement or merge candidates appear: read [[kernel/K03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].
- This run produces L-tier pages: read [[kernel/K12 Quality Assurance/12 Substantive Correctness Review#Substantive Correctness Review|Substantive Correctness Review]].
- Source-driven content involved: combine [[kernel/Read Sets/R04 Source-driven Expansion Read Set|Source-driven Expansion]].
- Expression Layer content involved: combine [[kernel/Read Sets/R05 Expression Layer Read Set|R05 Expression Layer]] and the artifact's profile binding or supplemental gate.
- Maintenance discovers or changes a corpus-wide capability gap, map entry, or planning owner: combine [[kernel/Read Sets/R13 Corpus Planning Read Set|R13 Corpus Planning]]. Ordinary page freshness does not rewrite the planning artifacts.
- Persistent, resumable, or multi-batch run: combine [[kernel/Read Sets/R07 Long-running Execution Read Set|R07 Long-running Execution]] and load [[kernel/K13 Task Runtime and Execution Control/12 Completion Gate Bindings|Completion Gate Bindings]].

A persistent multi-batch maintenance run also consumes the configured Corpus
Planning check/report through R07 even when this run does not change those
artifacts. It combines R13 only for an actual planning write-back.

## Gate

- Batch close: [[kernel/K12 Quality Assurance/14 Batch Review|Batch Review]], then [[kernel/K12 Quality Assurance/09 Batch-close Closed List|Batch-close Closed List]] at serial merge.
- Closing this run's manifest: [[kernel/K00 Standards Control/06 Completion Precedence and Task Contract#Maintenance Completion|Maintenance Completion]] — bounded completion semantics: the run is complete when the candidate manifest within the envelope is closed + the Ledger and watermark are advanced + each batch passes the applicable QA gates; the vault-wide Terminal Proof does not apply, and deferred items cut off by the envelope hand over to the next maintenance run and do not constitute a gap.
- When persistent state applies, close only after
  `check_queue.py --require-maintenance-complete` passes with explicit
  `--budget-manifest-receipt`, `--ledger-advance-receipt`, and
  `--watermark-advance-receipt` IDs. The gate also proves a nonempty Queue with
  zero remaining work, reconciled controls, terminal batches, and persisted
  applicable batch/close gates. Supply that canonical pass to the
  `--maintenance-completion-receipt` argument of
  `update_task.py --transition complete`; never enter `completion-candidate`
  and never run `check_proof.py`. If the task stops between gate and transition, reuse the
  pass only when resume reports it still compatible with current state and
  evidence.

## Related

- [[kernel/Read Sets/Read Sets Index|Read Sets Index]]
- [[kernel/K06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution]]
- [[kernel/K12 Quality Assurance Standard|Quality Assurance]]
