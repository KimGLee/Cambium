---
type: runtime-card
route_id: R11
read_set: kernel/Read Sets/R11 Large-scale Work Admission Read Set.md
compiled_from: '{{ standards_version }}'
source_files:
  - kernel/Read Sets/R11 Large-scale Work Admission Read Set.md
  - kernel/K00 Standards Control/13 Runtime Admission and Recovery.md
  - kernel/K00 Standards Control/06 Completion Precedence and Task Contract.md
  - kernel/K13 Task Runtime and Execution Control/02 Task Contract Binding and Time Semantics.md
  - kernel/K02 Knowledge Work Construction/01 Inventory and Coverage Ledger.md
  - kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md
  - kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries.md
  - kernel/K02 Knowledge Work Construction/05 Global Map Contract.md
  - kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract.md
  - kernel/K02 Knowledge Work Construction/07 Gap Register Contract.md
  - kernel/K13 Task Runtime and Execution Control/08 Required Queue Contract and Lifecycle.md
  - kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md
  - kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md
  - kernel/K12 Quality Assurance/13 Visual Verification Escalation.md
source_hash: 'f1124a4cee9b'
---
# R11 Large-scale Work Admission Card

> Compiled kernel guidance. This Card packages the existing large-scale Pre-execution Gate and authorizes no content operation by itself.

## Use When

Load before large-scale creation, moves, or deletion, together with [[kernel/Cards/R01 Core Bootstrap Card|R01 Core Bootstrap]] and the Card for the actual work. Ordinary local work does not load R11.

## Admission Checklist

- [ ] Record contract, scope, initial batch, Standards version, exact `selected_profile_manifest`, selected routes and Cards, actual source read-backs, target scope, exclusions, and latest user requirements.
- [ ] Make `minimum_run_until`, `checkpoint_at`, `hard_stop_at`, and the Completion Gate explicit; leave unspecified fields explicitly empty.
- [ ] Initialize `.cambium/` only when absent. If it exists, first run `check_queue.py --resume-status` and reconcile the recorded task; bind Coverage, Required Queue, and Progress to the same task, scope, Standards version, and selected profile.
- [ ] Reconcile Coverage with the file system and exclusions; inventory ownership, incoming links, user modifications, explicit batch manifests, and dependencies.
- [ ] Require Corpus Planning `applicability.state: configured`; reconcile the bound Global Map, Capability Matrix, and Gap Register and pass `Tools/check_corpus_plan.py`. Use R13 to create or repair them; R11 only consumes this admission condition.
- [ ] Compile the Queue from explicit Coverage inputs, record its path/revisions/fingerprint, and require `python3 Tools/check_queue.py .` plus `--require-ready <initial-batch-id>` to pass.
- [ ] Declare the initial batch simple with null/null or bind a current complex Work Spec whose batch ID and ordered manifest match the Queue.
- [ ] Identify foundational dependencies without burying shared foundations in the profile application mainline.
- [ ] For source-driven work, establish a source inventory and claim-extraction plan.
- [ ] Define batch acceptance, `rendering_mode`, deterministic checks, and the objective trigger plus unresolved question for any visual escalation.
- [ ] Load the latest Audit Receipt Register. Do not build an AuditPlan at task start; build it exactly once before batch close.
- [ ] Load the task-specific Card and resolve all triggered and future Gate modules.

## Gate

Execution may begin only when every applicable admission item is resolved, corpus planning passes, and the initial Queue item is ready. Missing, wrong-path, empty-by-error, inconsistent, held, or stale planning/runtime state is not an admission pass. If authority, ownership, scope, source evidence, a required dependency, or a recovery boundary remains unresolved, stay in planning or investigation.

## Read Back When

Read [[kernel/Read Sets/R11 Large-scale Work Admission Read Set|R11 Read Set]] and the canonical owner for complete Task Contract fields, Coverage reconciliation, time semantics, receipt planning, or visual escalation. Add R07 only for multi-batch, checkpoint, or resume behavior.
