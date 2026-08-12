# Cambium

English | [简体中文](README.zh-CN.md)

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
concrete scope, language, architecture, corpus-planning bindings and scale,
priorities, sources, roles, expression artifacts, audit bindings, scans, and
supplemental gates. A profile may extend defined interfaces, but it cannot
replace, disable, or weaken the kernel.

| Component | Responsibility |
|---|---|
| Kernel modules (`K00`-`K13`) | Normative, cross-domain rule text |
| Runtime routes (`R01`-`R13`) | Task-specific loading and execution paths; `Kxx` and `Rxx` are independent namespaces |
| Read Sets | Route-specific source-loading boundary used when a Runtime Card requires read-back |
| Runtime Cards | Kernel-owned, compiled shortcuts for routine agent execution; never a second source of rules |
| Selected profile | The adopter's concrete answers to the profile interface |
| Adopter runtime namespace (`.cambium/`) | Coverage object state, the canonical Required Queue, task-level Progress, hash-bound complex-batch Work Specs, controlled plans including active-task Standards adoption, deltas, receipts, and derived reports |
| Tools | Deterministic checks, controlled state writers, schemas, receipts, and derived/compiled-artifact generators; not final semantic judgment |

Within the kernel module namespace, [K02 Knowledge Work Construction](<kernel/K02 Knowledge Work Construction Standard.md>)
owns knowledge-object inventory, Coverage semantics, Corpus Planning,
architecture and dependency planning, knowledge-batch production, and
migration safety. [K13 Task Runtime
and Execution Control](<kernel/K13 Task Runtime and Execution Control Standard.md>)
owns the persistent runtime namespace, Task Contract and task state,
Guidance/Amendments, Progress Ledger, Required Queue, batch transitions,
hash-bound batch Work Specs, controlled active-task Standards-adoption state
writes, completion bindings, handoff, and interruption recovery. K12 remains
the sole owner of which changed Standards predicates affect a live task and
which gates must rerun. This boundary keeps
knowledge-object disposition separate from batch/work-unit lifecycle while
requiring the two state layers to reconcile.

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
  researcher, or independent reviewer. Acting as the independent reviewer is
  the narrowest of those roles: [`K12/12 Substantive Correctness
  Review`](<kernel/K12 Quality Assurance/12 Substantive Correctness Review.md>)
  requires a subagent started with a clean context and carrying no author
  context, whose input is only the note body and its Sources. An ordinary child
  context that inherits the author's context does not satisfy it.
- A logical **integrator** exclusively controls the shared state named in
  [`K13/10 Batch Admission Transitions and Serial Integration`](<kernel/K13 Task Runtime and Execution Control/10 Batch Admission Transitions and Serial Integration.md>):
  guidance disposition, Queue structural revision, Queue state transition,
  contract changes, Standards adoption, batch activation, and merging. That
  module states the enumeration; this list is a reader's summary of it.

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
├── work_specs/  # immutable restricted-YAML contracts for complex batches
├── deltas/      # worker deltas and restricted-YAML controlled-operation plans
├── receipts/    # deterministic and transition evidence
├── reports/     # derived human-readable views
└── tmp/         # recovery locks and incomplete-write metadata
```

`state/`, `work_specs/`, `deltas/`, and `receipts/` are durable. Reports are
projections, not tool inputs, and `tmp/` is ignored by Git; a surviving writer
lock remains recovery evidence until its operation is reconciled. Cambium
publishes the schemas under `Tools/schemas/`; a conformance fixture suite is
planned rather than shipped, and this repository carries none today (see
[`ROADMAP.md`](ROADMAP.md) `Observability And Conformance`). An adopter creates
its own runtime state with `Tools/init_state.py` after selecting a profile and
defining a task. The tool
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

The kernel and tools now provide persistent task and Required Queue state,
optional hash-bound complex-batch Work Specs, explicit Global Map / Capability
Matrix / Gap Register validation, and deterministic initialization,
compilation, validation, task/batch transitions, active-task Standards/Profile
adoption, interruption recovery, build Terminal closure, bounded maintenance
closure, and derived report generation. The page-level contract family is also
deterministic: the composed frontmatter page contract (K08/06-08, advisory
`page-contract` gate), the Structure Registry resolution (K01/05-06,
`structure-registry` gate) with its marker-block coverage projections, and the
page boundary contract (K08/09, advisory `boundary-contract` gate) with its
tool-owned boundary projection blocks.
They do not dispatch agents. Worker dispatch, workspace isolation, event
delivery, and the integrator loop must still be supplied by the adopting
runtime or a human operator.

The shipped Amendment interface first registers an approved operational
decision against the exact current state, then consumes that authorization in
a scope/disposition replan or batch-cancellation transaction. Pending
registration receipts authorize current execution; after verified write-back
they prove history only. A separate Standards-adoption transaction synchronizes
only the three Standards/Profile identities, the Progress load set, and the
structural Queue revision while preserving the task and every batch
lifecycle/hold. After
Queue materialization, a change to any other Task Contract field is rejected
unless a host supplies an equivalent controlled writer; the
baseline recovery path is to pause or cancel the current task, preserve its
runtime, and begin a successor task. A generic non-scope Contract Amendment
writer remains roadmap work.

These writers accept only the current public schema and receipt protocols. An
existing adopter runtime with older or unregistered operational Amendment
state must be converted outside the public execution path before it is loaded;
Standards adoption does not guess or silently upgrade that state.

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

Profile adoption follows one process whether the target corpus already exists
or will be built from zero, and Cambium never creates the corpus during setup.
The two differ in exactly one place, described under **Adopting into an empty
corpus** below: a corpus with pages is described from what it contains, and a
corpus without them is described from what its first batch will contain. Start
by creating a profile for that corpus. Do not edit the shared template in place
and do not copy an example as the starting point.

```text
cp -R profiles/_template profiles/my-profile
```

The template ships pre-closed: every slot switch with a legal exit state is
already in it, operational answers are pre-filled for confirmation, and only
the decisions no template can make remain open. To answer every switch now
instead, the adoption interview walks the closed ones in the same sitting.
Either route produces a fully conformant profile; the fill-depth contract is
in [`profiles/README.md`](profiles/README.md).

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
   and the frontmatter page contract, and regenerate the Runtime Cards for the
   adopted Standards version:

   ```text
   python3 Tools/compose_vocab.py
   python3 Tools/compose_page_contract.py
   python3 Tools/stamp_cards.py . --set-version YOUR_VERSION
   python3 Tools/stamp_cards.py . --check
   ```

5. Complete the R09 governance gates before beginning corpus-content work.
   [`Tools/README.md`](Tools/README.md) documents the individual commands,
   receipts, and exit semantics; tool success alone is not proof that the
   complete governance gate passed.

### Adopting into an empty corpus

Some of the profile's answers describe a corpus, and a corpus with no pages
cannot yet supply them. Two are satisfied by the first batch rather than before
it, and need no separate seeding task, second adoption, or relaxed contract. A
third is an open gap and is stated as one.

- **The residual scan.** Its matchers normally come from strings real pages
  carry. With no pages, declare the structure class you will use, and have the
  first batch create one page under the accepted root that carries it. The
  production scan refuses a configuration that recognises nothing in the
  repository, so a declared class must be materialized; the positive control
  proves only that matchers and `mandated_headings` agree and passes on an
  empty repository.
- **Coverage.** Knowledge objects that do not exist yet still get records, so
  the first Queue is compiled from pages you intend rather than pages you have.
- **Corpus Planning is the open one.** The Global Map names existing canonical
  owners, so an empty corpus cannot configure the slot, and
  [`K00/13`](<kernel/K00 Standards Control/13 Runtime Admission and Recovery.md>)
  admits large-scale work only against a configured plan. This revision records
  the ordering gap rather than working around it; see
  [`K02/03`](<kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md>).

Copying, filling, validating, or recording a manifest path does not activate a
profile by itself. The manifest becomes the selected profile for content work
only when the complete R09 initial-adoption change closes. Validate the filled
copy, not `_template`; the composed vocabulary does not exist before adoption.

## Adopt A New Standards Version Into An Active Task

R09 governs the Standards revision and records its exact changed predicates.
When an existing `.cambium/` task still freezes the prior Standards/Profile
identity, R09 produces one restricted-YAML plan using
[`Tools/schemas/standards_adoption_plan.template.yaml`](Tools/schemas/standards_adoption_plan.template.yaml):

```text
.cambium/deltas/standards-adoptions/<adoption-id>.yaml
```

That plan is the task's canonical machine revision record. It binds the
complete approved K00/03 bytes, deterministic after snapshots of `kernel/` and
the selected Profile directory, and the exact changed-predicate,
invalidated-evidence dimension/boundary, and rerun scope. There is no second
revision YAML or prose adoption copy.

R07 executes or resumes that plan. Dry-run first; only the integrator writes:

```text
python3 Tools/adopt_standards.py . \
  --plan .cambium/deltas/standards-adoptions/SA-001.yaml

python3 Tools/adopt_standards.py . \
  --plan .cambium/deltas/standards-adoptions/SA-001.yaml \
  --apply --actor-role integrator
```

The writer accepts only an `active` or `paused` task. If a build task is already
`completion-candidate`, first use the legal Task transition to return it to
`paused` or `active`; if the new Standards cannot validate a bound Work Spec,
upgrade that specification through its owning process before adoption. The
same preparation formally rolls back any affected `merge-ready` batch and
places every affected `open` batch under `revalidation-required`; the writer
verifies but does not create lifecycle/hold changes. The
transaction then preserves that Task state and every batch state/hold, keeps
Queue membership/order fixed, increments the structural `queue_revision`,
updates the synchronized Contract/Standards/Profile/load set, and appends
recoverable evidence. Historical receipt bytes remain unchanged.

Every adoption consumes immediate Queue consistency on staged after bytes.
Changed predicates select any additional deferred evidence boundaries: a
batch-close or Terminal gate reruns only when that boundary is reached and does
not block unrelated earlier work. Historical closed transitions continue to
verify under the identity that produced them; declared invalidated evidence cannot
be reused as current evidence under the new predicate. Current-use receipt
catalogs exclude every invalidated-evidence receipt ID accumulated by committed
adoptions.

The plan and append-only receipts are the Agent interface. Cambium does not
create or consume a persistent Markdown adoption report.

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
Coverage proposal, register its approved exact diff, and never require editing
canonical Coverage in advance.

Large-scale construction, migration, or persistent multi-batch corpus work
also configures the selected Profile's `Corpus Planning` slot. Maintain its
restricted-YAML Global Map, Capability Matrix, and Gap Register through R13,
then run `check_corpus_plan.py`. Agents consume its deterministic JSON
projection and the separate semantic-acceptance status instead of storing a
copied report. A Profile-bound authority records accepted/rejected Capability
decisions from restricted YAML with `record_corpus_acceptance.py`; evidence is
append-only JSONL. These artifacts supply explicit topology, capability,
priority, evidence, and gap-handoff inputs. They do not schedule Queue work or
replace Coverage.

A simple batch records `work_spec_path: null` and `work_spec_sha256: null`.
Only a complex batch creates a restricted-YAML contract directly under
`.cambium/work_specs/` from `Tools/schemas/batch_work_spec.template.yaml`, then
binds that exact path and SHA-256 in Coverage `batch_specs` before Queue
compilation. The Work Spec carries batch-specific outcome, instructions,
acceptance conditions, and constraints; Queue order, lifecycle, holds, and
receipts remain in the Required Queue.

```text
# Fill .cambium/state/coverage_ledger.yaml with the accepted inventory.
# Objects not yet created belong in it too; the Queue is compiled from what
# the task intends to build, not only from what the file system already holds.
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
holds, receipts, Amendment registration and execution, interruption recovery,
and both completion paths.

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
