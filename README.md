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
| Kernel modules (`K00`-`K12`) | Normative, cross-domain rule text |
| Runtime routes (`R01`-`R12`) | Task-specific loading and execution paths; `Kxx` and `Rxx` are independent namespaces |
| Read Sets | Route-specific source-loading boundary used when a Runtime Card requires read-back |
| Runtime Cards | Kernel-owned, compiled shortcuts for routine agent execution; never a second source of rules |
| Selected profile | The adopter's concrete answers to the profile interface |
| Tools | Deterministic checks, schemas, receipts, and compiled-artifact generators; not final semantic judgment |

Routine work starts from Runtime Cards. When a Card is incomplete, disputed,
or insufficient for an exception, the agent reads back its Read Set and the
referenced kernel modules. Normative source text always wins.

This repository is intentionally uninstantiated. The adopter-specific active
state in
[`K00/03 Standards Governance`](<kernel/K00 Standards Control/03 Standards Governance.md>)
still contains placeholders and no profile is selected. It therefore defines
no active standard for a particular knowledge corpus and distributes no
profile-specific `Tools/vocab.yaml`.

## Execution Model

Cambium separates durable work units from execution contexts.

- A **batch** is an independently accepted unit of work with its own manifest,
  dependencies, receipts, delta, and lifecycle.
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

## Current Implementation Boundaries

The kernel supports sequential execution and isolated concurrent batches, but
this repository does not yet ship an agent orchestrator or host adapter.
Worker dispatch, workspace isolation, scheduling, receipt collection, and the
integrator loop must currently be supplied by the adopting runtime.

Profile setup is also manual and file-based. Users copy `_template`, fill the
resulting profile, and validate it with `check_profile.py`; this release does
not include a profile questionnaire or configuration generator. Planned
convenience and runtime layers are described in [`ROADMAP.md`](ROADMAP.md).

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
