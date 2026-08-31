# Cambium

English | [简体中文](README.zh-CN.md)

Cambium is a governance standard and reference toolset for knowledge repositories maintained with LLM agents.

It helps an operator answer five practical questions:

1. What rules apply to this repository?
2. What work is required, and who may change shared state?
3. What evidence must exist before work can close?
4. How can an interrupted task resume without guessing?
5. Which decisions belong to the operator rather than the agent?

Cambium is not a knowledge base, a RAG engine, an agent scheduler, or a default domain policy. It governs work; it does not supply the corpus or decide its meaning.

## Start Here

- To understand the model, read [The Mental Model](#the-mental-model).
- To adopt Cambium for a repository, follow [Adopt Cambium](#adopt-cambium).
- To resume existing work, run the command in [Start Or Resume A Task](#start-or-resume-a-task) before writing anything.
- To connect an agent host, see [Use Cambium From An Agent Host](#use-cambium-from-an-agent-host).
- For every tool and its exact arguments, see [Tools/README.md](Tools/README.md).
- For what is complete, in progress, or only conditional, see [ROADMAP.md](ROADMAP.md).

## The Mental Model

```text
effective governance
  = Cambium kernel
  + exactly one selected profile
  + adopter-owned runtime state
```

The diagram shows how these layers connect to runtime routes, deterministic tools, and agent execution contexts.

![Cambium architecture overview](assets/readme/cambium-architecture-en.png)

| Layer | What it owns |
|---|---|
| `kernel/` | Cross-domain governance semantics, invariants, state meanings, and extension points |
| `Card/` | Curated, non-authoritative flight checklists for an already selected task route or phase |
| `Read Set/` | Machine-resolvable declarations of what canonical material an already selected route or phase must load |
| Selected profile | One repository's scope, language, architecture, sources, priorities, roles, scans, and allowed extensions |
| `.cambium/` | The adopter's current governance identity, task state, Queue, plans, deltas, receipts, and recovery evidence |
| `Tools/` | Stable public commands and Area/Domain implementations for deterministic checks, controlled writes, schemas, and generated projections |

The kernel is normative. A profile can fill or tighten an extension point, but cannot disable a kernel rule. Tools execute declared rules; they do not make the final semantic judgment.

Cards are short, curated checklists, not routes or a second copy of the standard. Read Sets own the static loading boundary. When a Card is insufficient or disputed, its read-back hook resolves through the paired Read Set to the canonical owner.

This repository is intentionally uninstantiated. It contains one candidate Profile template and non-authoritative examples, but selects no adopter profile and creates no fabricated task state.

## What Ships Today

Cambium currently provides:

- a single pre-closed profile template, a safe scaffolder, a machine-readable adoption interview, a read-only onboarding status view, and profile checks;
- persistent Coverage, Required Queue, and Progress state for resumable work;
- deterministic task and batch transitions, controlled Amendments, active-task Standards adoption, interruption recovery, and build or maintenance closure;
- append-only receipts and Terminal Proof bindings;
- explicit Global Map, Capability Matrix, and Gap Register validation;
- deterministic page, structure, vocabulary, link, boundary, freshness, and residual-content checks;
- a generated host-neutral interface: each tool's own CLI declaration and the closed agent-interface capability policy compile into the agent-facing MCP projection and per-host configuration; every active caller-visible path is retained as a descriptor capability through subprocess consumption;
- a typed Task Runtime Runner that advances registered deterministic tools to the next Agent, user, Host, repair, or terminal boundary;
- Card-first activation and progressive Read Set delivery primitives.

The generated MCP surface exposes both leaf calls and the bounded Runner. The Runner is not a scheduler or governance engine: it derives one identity-bound next action from current runtime state, invokes only registered capabilities, reads the result back, and stops at every semantic boundary. Each underlying Tool still decides whether its operation is valid and whether its evidence counts. For every active typed path, the transport retains the admitted file or parent-directory descriptor through subprocess consumption; an unsupported platform fails server initialization instead of claiming this assurance.

## What Does Not Ship Yet

Cambium does not currently bundle:

- agent dispatch or scheduling;
- isolated worker workspaces;
- a complete single-writer integrator loop;
- durable Assignment lifecycle management;
- authenticated actor or reviewer identity;
- protected whole-workspace execution against arbitrary concurrent mutation;
- automatic corpus-wide dependency propagation;
- an independent evaluator that re-derives the complete expected corpus;
- an installable OpenAI Plugin package, Hooks, UI, or marketplace entry.

These boundaries are intentional. A host may add capabilities, but it must not claim evidence for a capability it cannot prove. See [ROADMAP.md](ROADMAP.md) for the delivery order.

## The Three Runtime Ledgers

Long-running work uses three state objects with different owners:

| State object | What it answers |
|---|---|
| Coverage Ledger | Which knowledge objects exist, what disposition they have, and which batch currently owns unfinished work? |
| Required Queue | Which batches exist, what are their manifests and dependencies, and what lifecycle state is each batch in? |
| Progress Ledger | What is the task contract, whole-task state, checkpoint, Standards identity, and accepted Queue fingerprint? |

They must agree, but they are not interchangeable task lists.

The adopter-owned namespace contains six lifecycle classes:

```text
.cambium/
├── <canonical current state>
├── <bound operational inputs>
├── <evidence and history>
├── <recovery state>
├── <transient workspace>
└── <derived projections>
```

Do not edit canonical state by hand. Use the owning writer so revisions, hashes, receipts, and recovery evidence move together. [`Tools/execution/task_runtime/runtime_paths.py`](Tools/execution/task_runtime/runtime_paths.py) is the single machine owner of the current physical path spellings and object classifications; this README does not maintain a second directory contract.

## Adopt Cambium

Adoption creates and approves one profile for one repository. Copying a template or example does not select it.

### 1. Create a candidate profile

```text
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
```

The first command is a dry run. The second copies only the version-controlled whitelist and refuses to overwrite an existing candidate.

### 2. Answer the open decisions and validate

Use [profiles/interview.yaml](profiles/interview.yaml) with an assisting agent, or fill the same contract by hand. The common slot interface belongs to the Kernel and is defined by [K00/19](kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) and its machine-readable registry; [profiles/README.md](profiles/README.md) is the candidate workflow guide.

```text
python3 Tools/profile_onboarding_status.py . --profile-id my-profile --json
python3 Tools/check_profile.py profiles/my-profile
```

The template pre-closes choices that have a safe legal default. The remaining questions require operator-confirmed repository decisions. An agent may prepare a candidate, but may not approve it or invent domain policy.

### 3. Approve the profile through R09

Prepare a plan from [Tools/schemas/profile_adoption_plan.template.yaml](Tools/schemas/profile_adoption_plan.template.yaml), then dry-run and apply it:

```text
python3 Tools/apply_profile_adoption.py . --plan <plan>.yaml \
  --upstream-root <local-cambium-repository> --upstream-ref <git-ref>
python3 Tools/apply_profile_adoption.py . --plan <plan>.yaml \
  --upstream-root <local-cambium-repository> --upstream-ref <git-ref> --apply
```

The transaction resolves the upstream ref to its full Git commit SHA and records that SHA as the sole Standards identity in `upstream_revision_id`. It binds the selected Profile and resulting adopter-owned contracts/evidence, and restores the previous control plane if any step fails. It never restamps or rewrites the adopter's upstream Card bytes. Adoption remains an explicit CLI maintenance operation: its external upstream repository input is never exposed as an unrestricted MCP argument.

An empty corpus follows the same adoption contract. First perform bounded founding work to create real canonical owners and the residual-scan witness — one page may serve as both owner and witness when that is semantically natural, but pages are never merged only to save files. Then a second R09 revision configures the Corpus Planning slot before large-scale work begins. The candidate and adoption boundary is documented in [profiles/README.md](profiles/README.md#mechanical-validation-and-adoption).

## Start Or Resume A Task

Always check for existing runtime state before writing:

```text
python3 Tools/check_queue.py . --resume-status
```

If `.cambium/state/` exists, this command reports the recorded task, locks, holds, in-flight batches, recovery state, and exact `next_action`. Do not initialize over it.

Bounded work does not need persistent state. For long-running, resumable, or multi-batch work, first copy and complete the single Task Plan:

```text
cp Tools/schemas/task_plan.template.yaml \
  .cambium/deltas/task-plans/TP-001.yaml

python3 Tools/init_state.py . \
  --plan .cambium/deltas/task-plans/TP-001.yaml

python3 Tools/init_state.py . \
  --plan .cambium/deltas/task-plans/TP-001.yaml --apply

# Run the exact compile_queue command printed by init_state.py; it already carries the Queue revision and SHA bound to the published Task Plan.
python3 Tools/compile_queue.py . --apply --actor-role integrator \
  --expected-queue-revision REVISION \
  --expected-sha256 SHA256

python3 Tools/check_queue.py .
python3 Tools/render_queue.py .
```

`init_state.py` has no parallel flags for task identity, objective, scope, Standards, Profile, completion model, or concurrency. Those confirmed values have one owner: the Task Plan. The command atomically publishes the empty Queue, complete Task Contract, planning-only Coverage, and the Receipt retained by Progress; `compile_queue.py` remains the sole Queue materializer.

## Controlled Changes

After the Queue exists, shared state changes go through a controlled writer:

- `register_amendment.py` and `apply_amendment.py` handle approved operational replans such as bounded scope/disposition changes and batch cancellation;
- `apply_contract_amendment.py` handles the two supported Task Contract fields: `policy_exceptions` and `amendment_authority`;
- `adopt_standards.py` moves an active task to an approved Standards/Profile revision without rewriting its lifecycle history;
- `apply_delta.py`, `update_queue.py`, and `update_task.py` own batch and task progression.

Writers are dry runs unless `--apply` is present. Shared-state writes are integrator-only and require current revisions or hashes where the tool asks for them. Exact commands, schemas, and recovery procedures are in [Tools/README.md](Tools/README.md).

## Use Cambium From An Agent Host

Cambium renders registration and corpus binding for Claude Code, Codex, Kimi Code, and dsh from one canonical server definition:

```bash
python3 Tools/render_host_configs.py . \
  --projection-target carried-runtime \
  --output-dir /absolute/path/to/corpus/.host-config-staging \
  --distribution-root /absolute/path/to/corpus \
  --workspace-root /absolute/path/to/corpus

python3 Tools/render_host_configs.py . \
  --projection-target carried-runtime \
  --output-dir /absolute/path/to/corpus/.host-config-staging \
  --distribution-root /absolute/path/to/corpus \
  --workspace-root /absolute/path/to/corpus \
  --check
```

Run this from the adopted corpus root after its carried interface has been generated. Bound products land in `.host-config-staging/`; install the selected product through the host's own mechanism. `Tools/compiled/host-configs/` remains the source-distribution template set and is only regenerated or checked by Cambium maintenance.

| Host | Install the generated configuration at |
|---|---|
| Claude Code | `<corpus>/.mcp.json` |
| Codex | `<corpus>/.codex/config.toml` |
| Kimi Code | `<corpus>/.kimi-code/mcp.json` |
| dsh | the operator profile for registration and `<corpus>/.env` for binding |

Registration answers “where is the server?” Corpus binding answers “which repository does this session govern?” They are separate capabilities.

Installing a host configuration is not Cambium adoption. It does not approve a profile, create task state, or migrate Standards. The MCP server exposes the generated CLI projection and passes tool verdicts through; it does not create a second policy engine.

Card delivery also has a strict evidence boundary. A server can prove what it sent, but not by itself what a host placed in the model context or what an agent read. Machine-enforced Assignment delivery remains an in-progress roadmap capability; until its gate is complete, do not turn transport metadata into a claim of cognition or independent execution.

## Safety And Trust Boundary

- A surviving writer lock is recovery evidence. Do not delete it until the writer, state files, receipts, pending deltas, and archive moves are reconciled.
- Component-byte comparison must run from a separately trusted upstream checkout (or protected runner) against the adopter. It detects drift but cannot make an adopter's unchecked Tool copy authenticate itself.
- JSONL receipts are append-only. An uncertain append keeps the lock rather than guessing whether the receipt landed.
- Exit code `2` is a hold, not success and not an ordinary failure.
- Reports and generated projections are views, never canonical input.
- Repository-provided verifier code is not run automatically; its source and effects require explicit authorization.

SHA-256 bindings detect drift and inconsistent history inside the adopter's local trust domain. They are not signatures. Without a protected runner or external attestation, Cambium does not authenticate actor labels, reviewer labels, operating-system identities, or workspace isolation. A party that can rewrite the repository, tools, and evidence can construct a new internally consistent history. The MCP transport rejects unsafe arguments and static path aliases inside this local trust domain. For every caller-visible typed path, it also prevents a post-admission name or parent replacement from redirecting the child tool: the exact admitted object is retained and consumed. This is not protected whole-workspace execution. A concurrently privileged process can still attack fixed or derived internal paths that are not part of the public call surface, rewrite repository code and evidence together, or interfere outside the filesystem capability boundary; those wider guarantees require an isolated workspace or external trust anchor.

## Repository Map

| Path | Purpose |
|---|---|
| [`kernel/`](kernel/) | Normative common governance rules and Kernel-owned machine contracts |
| [`Card/`](Card/) | Curated, non-authoritative action checklists |
| [`Read Set/`](Read%20Set/) | Canonical static loading declarations and generated navigation |
| [`profiles/`](profiles/) | Candidate template, interview, adoption guidance, and non-authoritative examples |
| [`Tools/`](Tools/) | Stable `Tools/<tool>.py` public commands, Tool contracts, schemas, and operating guidance |
| [`Tools/governance/`](Tools/governance/), [`Tools/knowledge/`](Tools/knowledge/), [`Tools/execution/`](Tools/execution/), [`Tools/platform/`](Tools/platform/) | Implementations grouped by the machine-checked Area/Domain hierarchy |
| [`Tools/TOOL_CATALOG.md`](Tools/TOOL_CATALOG.md) | Generated Tool hierarchy, interface, and dependency navigation |
| [`Tools/compiled/`](Tools/compiled/) | Generated CLI, MCP, metadata, host, and Tool-catalog projections |
| [`assets/readme/`](assets/readme/) | Public diagrams embedded by the root READMEs |
| [`ROADMAP.md`](ROADMAP.md) | Status-based implementation roadmap |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Issue ownership, defect promotion, and pull-request contract |

Kernel module numbers are stable identities, not a contiguous display sequence. A number is not reused after its module moves or retires; the active reading order is the one listed by each Standard entry page's Module Index.

Examples show answer shape; they are not defaults and must not be selected in place of an adopter-owned profile.

## License

Cambium uses path-based licensing:

- software and repository-engineering material under `Tools/`, `.github/`, `Makefile`, and `distribution-boundary.yaml` uses Apache-2.0;
- standards under `kernel/`, curated `Card/` and `Read Set/` material, profiles, README and contributing documentation, the roadmap, and diagrams under `assets/readme/` use CC BY 4.0.

See [LICENSE.md](LICENSE.md), [ATTRIBUTION.md](ATTRIBUTION.md), and [LICENSES/](LICENSES/) for the authoritative terms and notices.

Adopter-generated profiles, state, receipts, and evidence do not acquire a Cambium license merely because Cambium tools manage them.
