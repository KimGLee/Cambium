# Cambium

Cambium is a governance standard and reference toolset for knowledge corpora
maintained with LLM agents. It defines how an agent loads rules, scopes work,
preserves canonical ownership, incorporates sources, manages long-running
changes, and produces auditable evidence before claiming completion.

Cambium does not provide a knowledge corpus, a RAG engine, or a default domain
policy. It governs how an operator and an agent maintain a corpus over time.

## Architecture

```text
effective standard = domain-neutral kernel + exactly one selected profile
```

The kernel owns the cross-domain rules. A profile supplies one corpus's
concrete scope, language, architecture, priorities, sources, roles, expression
artifacts, audit bindings, scans, and supplemental gates. A profile may extend
defined interfaces, but it cannot replace, disable, or weaken the kernel.

| Component | Responsibility |
|---|---|
| Kernel modules (`K00`-`K13`) | Normative, cross-domain rule text |
| Runtime routes (`R01`-`R12`) | Task-specific loading and execution paths; `Kxx` and `Rxx` are independent namespaces |
| Read Sets | Route-specific source-loading boundary used when a Runtime Card requires read-back |
| Runtime Cards | Kernel-owned, compiled shortcuts for routine agent execution; never a second source of rules |
| Selected profile | The adopter's concrete answers to the profile interface |
| Adopter runtime state (`.cambium/`) | Coverage object state, the canonical Required Queue, task-level Progress, deltas, and receipts |
| Tools | Deterministic checks, schemas, receipts, and compiled-artifact generators; not final semantic judgment |

Routine work starts from Runtime Cards. When a Card is incomplete, disputed,
or insufficient for an exception, the agent reads back its Read Set and the
referenced kernel modules. Normative source text always wins.

This repository is intentionally uninstantiated. The adopter-specific active
state in
[`K00/03 Standards Governance`](<kernel/K00 Standards Control/03 Standards Governance.md>)
still contains placeholders and no profile is selected. It therefore defines
no active standard for a particular knowledge corpus and distributes no
profile-specific `Tools/vocab.yaml` or fabricated `.cambium/state/`.

## Execution Model

Cambium separates durable work units from execution contexts.

- A **batch** is an independently accepted unit of work with its own manifest,
  dependencies, receipts, delta, and lifecycle.
- The **Required Queue** is the model-neutral, persistent owner of those batch
  manifests, their deterministic order, dependencies, holds, and lifecycle.
- An **agent** is an execution context assigned to work. One agent may execute
  several batches sequentially, while isolated agents may execute disjoint
  batches concurrently.
- A **subagent** is a child execution context created by a runtime. It is not a
  separate Cambium work unit or authority class and may act as a worker,
  researcher, or independent reviewer.
- A logical **integrator** exclusively controls shared state, batch activation,
  queue changes, and serial merges.

The active-batch concurrency limit is not an agent-count limit. Concurrent
workers produce isolated batch outputs; the integrator merges those outputs
one at a time and runs the global checks after each merge.

Three machine-readable control objects deliberately have different jobs:

| State object | Owns |
|---|---|
| Coverage Ledger | Knowledge objects, dispositions, canonical owners, and object-side batch assignment |
| Required Queue | Batch/work-unit manifests, order, dependencies, lifecycle, holds, and transition evidence |
| Progress Ledger | Task Contract, whole-task state, Guidance/Amendments, checkpoints, and the accepted Queue fingerprint |

They are reconciled rather than treated as interchangeable task lists.

## Repository Layout

| Path | Contents |
|---|---|
| [`kernel/`](kernel/) | Cross-domain standards, Read Sets, and compiled Runtime Cards |
| [`profiles/README.md`](profiles/README.md) | The authoritative profile-slot interface and filling rules |
| [`profiles/_template/`](profiles/_template/) | A domain-neutral form to copy and fill; not a runnable or default profile |
| [`profiles/examples/`](profiles/examples/) | Non-normative completed references; examples are not adoption starting points and cannot be selected in place |
| [`Tools/`](Tools/) | Standard-library Python checks, schemas, receipts, and compiled-artifact generators |
| [`ROADMAP.md`](ROADMAP.md) | Non-normative implementation directions; not a statement of current capability |

The included
[`Agent Systems Atlas`](profiles/examples/agent-atlas/README.md) profile is an
example of answer shape and specificity. It is not Cambium's default
configuration and does not contain the Atlas knowledge corpus.

## Adopter Runtime State

Long-running, resumable, or multi-batch work uses one fixed namespace in the
adopting repository. Every task first checks whether that namespace already
exists, because a seemingly bounded new request may enter a repository whose
earlier persistent task was interrupted:

```text
.cambium/
├── state/       # Coverage, Required Queue, and Progress
├── deltas/      # worker-to-integrator batch deltas
├── receipts/    # deterministic and transition evidence
├── reports/     # derived human-readable views
└── tmp/         # recovery locks and incomplete-write metadata
```

`state/`, `deltas/`, and `receipts/` are durable. Reports are projections, not
tool inputs, and `tmp/` is ignored by Git; a surviving writer lock remains
recovery evidence until its operation is reconciled. Cambium publishes the schemas and
conformance fixtures; an adopter creates its own runtime state with
`Tools/init_state.py` after selecting a profile and defining a task. The tool
requires an explicit objective and exclusions, does not invent Required work,
and does not overwrite any existing `.cambium/` namespace.
If the namespace already exists, a restarted or newly assigned Agent first
runs `Tools/check_queue.py . --resume-status` to discover the recorded task,
its `build` or `maintenance` completion semantics, checkpoint binding, latest
task transition, in-flight batches, pending control inputs/deltas, the
applicable completion block, maintenance candidate SHA/partition and prior
completion anchor, holds, writer-lock evidence, and the exact
machine-readable `next_action`. A complete open-batch handoff is reported as
`admit-delta`; a merge-ready batch without an apply receipt becomes
`apply-delta`, and an applied batch without a current close bundle becomes
`run-batch-close-gate`. Only a current bundle authorizes the four-ID
`close-applied-batch` action and its exact copyable close command. This prevents
a fresh Agent context from mistaking an interrupted repository for an unused
one.

## Current Implementation Boundaries

The kernel and tools now provide persistent task and Required Queue state plus
deterministic initialization, compilation, validation, task/batch transitions,
interruption recovery, build Terminal closure, bounded maintenance closure,
and report generation. They do not
dispatch agents. Worker dispatch, workspace isolation, event delivery, and the
integrator loop must still be supplied by the adopting runtime or a human
operator.

The shipped Amendment transaction covers scope/disposition replans and batch
cancellation. After Queue materialization, a change to other Task Contract
fields is rejected unless a host supplies an equivalent controlled writer; the
baseline recovery path is to pause or cancel the current task, preserve its
runtime, and begin a successor task. A generic non-scope Contract Amendment
writer remains roadmap work.

Profile setup is also manual and file-based. Users copy `_template`, fill the
resulting profile, and validate it with `check_profile.py`; this release does
not include a profile questionnaire or configuration generator. Planned
convenience and runtime layers are described in [`ROADMAP.md`](ROADMAP.md).

Cambium's receipts and Terminal Proof operate inside the adopting repository's
local trust boundary. The shipped checks can validate receipt structure,
declared producer and version labels, exact SHA-256 bindings to current state
and content, transition-chain agreement, and whether evidence is stale. Those
hashes are integrity bindings, not signatures: without an external signing or
controlled-execution system, Cambium does not authenticate which executable
ran, which operating-system account supplied an actor label, or whether the
recorded reviewer was a different person or process. An adversary who may
rewrite the repository, its tools, and its evidence can construct an
internally consistent history. The baseline therefore detects accidental
drift, incomplete transitions, and stale or inconsistent evidence; stronger
provenance requires controls outside this repository.

## Adopt Cambium

Profile adoption follows the same process whether the target corpus already
exists or will be built from zero; Cambium does not create the corpus during
setup. Start by creating a profile for that corpus. Do not edit the shared
template in place and do not copy an example as the starting point.

```text
cp -R profiles/_template profiles/my-profile
```

1. Replace every `TODO(profile)` in `profiles/my-profile/`. Keep `profile_id`
   equal to the directory name and use
   [`profiles/README.md`](profiles/README.md) as the interface authority.
2. Validate the filled copy:

   ```text
   python3 Tools/check_profile.py profiles/my-profile
   ```

3. Perform initial adoption through the full
   [`R09 Standards Governance Read Set`](<kernel/Read Sets/R09 Standards Governance Read Set.md>).
   Record the adopter's Standards version, status `approved`, effective date,
   and exact `profiles/my-profile/profile.md` path in K00/03. Directory presence,
   profile discovery, an example, or a generated file never selects a profile.
4. With those candidate state fields in place, compose the profile vocabulary
   and regenerate the Runtime Cards for the adopted Standards version:

   ```text
   python3 Tools/compose_vocab.py
   python3 Tools/stamp_cards.py . --set-version YOUR_VERSION
   python3 Tools/stamp_cards.py . --check
   ```

5. Complete the R09 governance gates before beginning corpus-content work.
   [`Tools/README.md`](Tools/README.md) documents the individual commands,
   receipts, and exit semantics; tool success alone is not proof that the
   complete governance gate passed.

Copying, filling, validating, or recording a manifest path does not activate a
profile by itself. The manifest becomes the selected profile for content work
only when the complete R09 initial-adoption change closes. Validate the filled
copy, not `_template`; the composed vocabulary does not exist before adoption.

## Start A Governed Task

After initial adoption:

```text
Standards Overview
  -> Card Index
  -> R01 Core Bootstrap Card + the task-specific Runtime Card
  -> selected-profile bindings
  -> Read Set and kernel source read-back when required
  -> applicable gates, deterministic checks, and receipts
```

Begin with the
[`Standards Overview`](<kernel/K00 Standards Overview.md>) and
[`Kernel Runtime Card Index`](<kernel/Cards/Card Index.md>). Load only the
route, profile bindings, and source modules required by the current task.
Combine additional routes only when their Card Index triggers apply; they do
not replace the route for the work itself.

For every task, first inspect the target repository for `.cambium/`. If it
exists, do not write content or state and do not initialize or overwrite it:
inspect and reconcile its current task first. If it is absent, only a
long-running, resumable, or multi-batch task initializes it; bounded work
continues without creating empty runtime state.

```text
# Existing runtime state: always inspect before writing.
python3 Tools/check_queue.py . --resume-status

# No .cambium/ exists and persistent state applies: initialize once.
python3 Tools/init_state.py . \
  --task-id YOUR_TASK \
  --objective "State the concrete outcome this task must achieve" \
  --exclude "State one explicit out-of-scope boundary" \
  --completion-semantics build \
  --scope-version s1 \
  --standards-version YOUR_VERSION \
  --profile-manifest profiles/my-profile/profile.md \
  --apply
```

Choose `build` for corpus-building work that closes through
`completion-candidate`, R08, and Terminal Proof. Choose `maintenance` for an
R10 budget-envelope run that closes through the maintenance completion gate
without entering `completion-candidate`. The choice is required and frozen in
the Task Contract; initialization never guesses it. A bounded single-note task
does not initialize `.cambium/` merely to record this choice.

A reported writer lock may belong to a live writer or an interrupted write.
Do not delete it until no writer remains and the state files, receipts,
revisions/fingerprint, pending deltas, and any recorded archive move have been
reconciled. JSONL receipts are append-only; an uncertain receipt append keeps
the lock instead of deleting or rewriting evidence. A new task does
not reuse an old namespace, even when the old task is complete or cancelled;
an explicit archive/rollover process must handle that history. Cambium does not
yet automate rollover.

Once the current task is known and valid, inventory Required objects into
Coverage, declare explicit `batch_specs`, compile the Queue, and run
`check_queue.py` before activating a batch. Simple single-note work does not
need an empty Queue merely to satisfy a formality. The initial compile stores
an immutable origin receipt in Progress; later same-scope replans use a staged
Coverage proposal and never require editing canonical Coverage in advance.

```text
# Fill .cambium/state/coverage_ledger.yaml with the accepted inventory.
python3 Tools/compile_queue.py . --output .cambium/tmp/queue-proposal.yaml
python3 Tools/compile_queue.py . --apply --actor-role integrator \
  --expected-queue-revision 1 \
  --expected-sha256 SHA_PRINTED_BY_INIT
python3 Tools/check_queue.py .
python3 Tools/render_queue.py .
```

Lifecycle writes are dry runs unless `--apply` is supplied, and an apply also
requires the current revision/fingerprint printed by the state tools. See
[`Tools/README.md`](Tools/README.md) for transition commands, exit code 2
holds, receipts, Amendment-bound scope/cancellation transactions, interruption
recovery, and both completion paths.

## License

Cambium assigns licenses by path to its maintained, tracked release files:

- Software and implementation materials under [`Tools/`](Tools/) are licensed
  under the Apache License 2.0.
- The standards, profile materials, and project documentation under
  [`kernel/`](kernel/), [`profiles/`](profiles/), this README, and
  [`ROADMAP.md`](ROADMAP.md) are licensed under CC BY 4.0.

See [`LICENSE.md`](LICENSE.md) for the authoritative scope,
[`ATTRIBUTION.md`](ATTRIBUTION.md) for attribution guidance, and
[`LICENSES/`](LICENSES/) for the complete license texts.

Adopter-generated profiles, vocabularies, receipts, and runtime evidence do
not acquire a Cambium license merely because they are stored inside these
directories.
