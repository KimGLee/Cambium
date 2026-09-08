# Tools: deterministic execution for Cambium

`Tools/` contains Cambium's deterministic programs. This README provides navigation and operating guidance; linked owners define the contracts.

Most Python mechanics use the standard library. The Agent starts with [Host preparation](#host-preparation), which composes the TOML/CUE and optional rendering providers. Dependency bindings belong to Host configuration, not Profile or `.cambium`.

## Responsibility boundary

Tools own algorithms, interfaces, validation, controlled writes, projections, diagnostics, and implemented capabilities' result guarantees.

Tools do not judge knowledge quality, invent governance rules, authorize Profile or route choices, or treat an asserted actor name as authentication. Adoption writers execute authorized selections; candidate tools do not authorize adoption.

| Component | Owns | How Tools may interact with it |
|---|---|---|
| [`kernel/`](../kernel/) | Common governance rules and implementation-independent contracts | Validate or execute a named rule without restating it here |
| [`profiles/`](../profiles/) | One knowledge base's confirmed custom requirements | Validate confirmed values and consume stable bindings |
| [`Card/`](../Card/) | Curated, short action checklists | Check structure/currentness and deliver the selected projection |
| [`Read Set/`](<../Read Set/>) | Static loading relationships | Parse and resolve declared loading edges |
| `.cambium/` | One adopter's current state, bound inputs, evidence, recovery material, transient work, and derived projections | Read or change registered objects through the responsible checker or writer |
| [`Tools/`](./) | Deterministic implementation and Tool-owned machine contracts | Provide the program, diagnostics, and verifiable result |

A checker observes without repairing. A writer changes only its named transaction through an explicit mode such as `--apply`. Process success alone does not prove resulting state; critical writers perform required read-back.

## Layered organization

[`tool-taxonomy.yaml`](tool-taxonomy.yaml) owns the Area/Domain/Layer vocabulary; [`module-boundaries.yaml`](module-boundaries.yaml) assigns modules and constrains dependencies. These paths navigate that classification:

| Physical Area | Domains |
|---|---|
| [`governance/`](governance/) | `standards/`, `profile/`, `control/` |
| [`knowledge/`](knowledge/) | `structure/`, `metadata/`, `content/`, `rendering/` |
| [`execution/`](execution/) | `planning/`, `task_runtime/`, `audit/`, `evidence/`, `context_delivery/` |
| [`platform/`](platform/) | `agent_interface/`, `distribution/`, `repository/`, `common/` |

`Tools/<tool>.py` wrappers forward to their Area/Domain owners. Layer (`entrypoint`, `application`, `contract`, `infrastructure`, `api`) is not another directory level. Shared mechanics live in [`platform/common/`](platform/common/); task state in [`execution/task_runtime/`](execution/task_runtime/), including [`queue_runtime/`](execution/task_runtime/queue_runtime/).

`python3 Tools/module_boundary_report.py --format hierarchy` and [`TOOL_CATALOG.md`](TOOL_CATALOG.md) are generated views. The Catalog is distribution-only: adopters carry the runtime subset, not this source-tree inventory.

## Canonical navigation

Follow these owners instead of copying their field lists:

| Concern | Owner and implementation entry points |
|---|---|
| Gate identities and producers | [K00/12](<../kernel/K00 Standards Control/12 Control Registry.md>), [`control-registry.yaml`](<../kernel/K00 Standards Control/control-registry.yaml>) |
| Profile semantics and admission | [`profile-interface.yaml`](<../kernel/K00 Standards Control/profile-interface.yaml>), [`profile_contract.py`](governance/profile/profile_contract.py), [`profile_admission.py`](governance/profile/profile_admission.py), [`check_profile.py`](check_profile.py) |
| Profile storage and source mapping | [`profile-encoding.yaml`](governance/profile/profile-encoding.yaml), [`profile_layout_contract.py`](governance/profile/profile_layout_contract.py) |
| Corpus Planning | [`corpus-planning-contract.yaml`](<../kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml>), [`corpus_planning_contract.py`](execution/planning/corpus_planning_contract.py) |
| Audit dimensions and plan | [`audit-dimension-base.yaml`](<../kernel/K12 Quality Assurance/audit-dimension-base.yaml>), [`audit-plan-contract.yaml`](<../kernel/K12 Quality Assurance/audit-plan-contract.yaml>) |
| Review and receipt contracts | [K12/12](<../kernel/K12 Quality Assurance/12 Substantive Correctness Review.md>), [K12/14](<../kernel/K12 Quality Assurance/14 Batch Review.md>), [`audit-receipt-contract.yaml`](<../kernel/K12 Quality Assurance/audit-receipt-contract.yaml>) |
| Batch-close checklist | [`batch-close-closed-list.yaml`](<../kernel/K12 Quality Assurance/batch-close-closed-list.yaml>), [`batch_close_contract.py`](execution/audit/batch_close_contract.py) |
| Policy extensions | [`contract-exception-policy-base.yaml`](<../kernel/K00 Standards Control/contract-exception-policy-base.yaml>) |
| Installed scan and operation capabilities | [`scan-capabilities.yaml`](scan-capabilities.yaml), [`operation-capabilities.yaml`](operation-capabilities.yaml) |
| Card structure and size | [`card.schema.yaml`](schemas/card.schema.yaml), [`card-budget.yaml`](../Card/card-budget.yaml) |
| Read Set loading | [`read-set.schema.yaml`](<../Read Set/read-set.schema.yaml>), [`read_set_contract.py`](execution/context_delivery/read_set_contract.py) |
| Vocabulary and property state | [`vocabulary-base.yaml`](<../kernel/K08 Metadata and Status/vocabulary-base.yaml>), [`metadata_property_state.py`](knowledge/metadata/metadata_property_state.py) |
| Runtime lifecycle and paths | [`runtime-state-model.json`](<../kernel/K13 Task Runtime and Execution Control/runtime-state-model.json>), [`runtime_paths.py`](execution/task_runtime/runtime_paths.py) |
| Coverage and Work Spec | [`coverage_contract.py`](execution/planning/coverage_contract.py), [`work_spec_contract.py`](execution/planning/work_spec_contract.py) |
| Public interface and Host observations | [`agent-interface-policy.yaml`](agent-interface-policy.yaml), [`host-conformance.yaml`](host-conformance.yaml) |
| Module dependencies | [`module-boundaries.yaml`](module-boundaries.yaml), [`module_boundary_facts.py`](platform/distribution/module_boundary_facts.py), [`module_boundary_report.py`](module_boundary_report.py) |
| Upstream component boundary | [`distribution-boundary.yaml`](../distribution-boundary.yaml), [`upstream_identity.py`](platform/distribution/upstream_identity.py), [`upstream_component_boundary.py`](platform/distribution/upstream_component_boundary.py), [`check_upstream_components.py`](check_upstream_components.py) |
| Kernel leaf size | [`kernel-size-policy.yaml`](kernel-size-policy.yaml), [`kernel-size-exceptions.md`](kernel-size-exceptions.md), [`check_kernel_size.py`](check_kernel_size.py) |
| Writer input templates | [`schemas/`](schemas/) |

[`compiled/`](compiled/) contains generated projections. Each parser owns invocation shape; use `--help`. Source and module boundaries describe support libraries.

## Quick verification

List the adopter Gate sweep without executing it, then run it:

```text
python3 Tools/run_gates.py . --list
python3 Tools/run_gates.py .
```

Verify adopter bytes against the resolved full upstream SHA and its distribution boundary:

```text
python3 Tools/check_upstream_components.py <adopter-root> --upstream-root <cambium-git-root> --revision <git-ref> --check-manifest
```

Run it from a separately trusted upstream checkout. A clean `--write-manifest` writes only `.cambium/derived/upstream-component-byte-manifest.tsv`; unregistered executable artifacts fail.

Card currentness and Kernel size are independent repository-engineering Tool preflights, not Kernel Gates:

```text
python3 Tools/stamp_cards.py . --check
python3 Tools/check_kernel_size.py .
```

`stamp_cards.py --check` checks schema-selected Card budget, bindings, pairing and navigation, not meaning or Agent understanding. Card bytes remain immutable and unbound to adopter Standards.

`kernel-size-policy.yaml` owns numeric limits. The checker distinguishes hard failure (`1`) from engineering review (`2`).

## Host preparation

With Python 3.10 or later and a terminal-capable Agent, observe first, then apply within Host installation authorization:

```sh
python3 Tools/prepare_host.py . --json
python3 Tools/prepare_host.py . --apply --json
```

Tool owners supply versions and paths. Preparation verifies private Python/CUE resources and publishes Host bindings; it does not modify system Python, global PATH, Profile or runtime state. Add `--rendering` for selection or `--construct` for [rendering capabilities](knowledge/rendering/README.md).

For registration add `--host codex --workspace-root /absolute/corpus`. Unrelated settings are preserved; `--replace-host-overrides` replaces Python/CUE and removes explicit rendering paths. See `--help` for configuration-only mode and carried-runtime roots. Invalid overrides never silently fall back.

Follow the returned `inspect_host` request through the actual consumer. Prepared resources, installed configuration and process readiness are separate results; native patches/reloads remain Host handoffs. Pure MCP can observe but cannot install externally. Then query the original Runner: preserve completed actions and history, do not rebuild Task/AuditPlan, and let existing evidence owners recheck currentness.

## Profile toolchain

Dependency owners are [`requirements-profile.txt`](requirements-profile.txt), [`cue-toolchain.json`](governance/profile/cue-toolchain.json) and the separate Host editor [`requirements-host.txt`](requirements-host.txt). Host and CI share the [CUE installer](platform/distribution/install_profile_toolchain.py). Explicit `CAMBIUM_CUE` precedes managed discovery; an unusable evaluator returns a Host handoff, not a Profile verdict.

Kernel owns slot semantics; Tool owns encoding and evaluation. Generate CUE projections and [`profile-document.cue`](governance/profile/profile-document.cue) from their existing YAML owners:

```sh
python -m Tools.governance.profile.profile_schema_projection --root . --check
python -m Tools.governance.profile.profile_schema_projection --root . --write
```

`--check` is read-only; `--write` updates projections only. Admission verifies them against source bytes in the same snapshot. See the [Profile guide](../profiles/README.md).

## Profile candidate workflow

A Profile starts through user/Agent discussion. Source-distribution tools create `profiles/<profile-id>/profile.toml` from the single empty template; unanswered slots remain drafts, not confirmed defaults.

Preview, authorize and read back:

```text
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
python3 Tools/profile_candidate.py . --profile-id my-profile --mode read --json
python3 Tools/profile_candidate.py . --profile-id my-profile --mode render
```

[`profile_candidate.py`](profile_candidate.py) edits require a fresh snapshot hash, edit file, and `--apply`; they do not adopt. See [selectors and currentness](../profiles/README.md#agent-read-edit-and-review).

Follow [`profiles/interview.yaml`](../profiles/interview.yaml), then inspect unresolved decisions and validate:

```sh
python3 Tools/profile_onboarding_status.py . --profile-id my-profile --json
python3 Tools/check_profile.py profiles/my-profile --root .
```

Status, rendered views and CUE checks do not authorize adoption. For a confirmed initial plan:

```text
python3 Tools/apply_profile_adoption.py --help
python3 Tools/apply_profile_adoption.py . --plan <root-relative-plan.yaml> \
  --upstream-root <local-cambium-git-root> --upstream-ref <git-ref>
```

Omit `--apply` to preview. Later Standards/Profile changes use `adopt_standards.py` under [K12/10](<../kernel/K12 Quality Assurance/10 Standards Version Adoption.md>), not direct edits to runtime files.

For Profile revisions, use a matching source checkout's authoring kit; do not copy it into runtime or reset onboarding. [`distribution-boundary.yaml`](../distribution-boundary.yaml) separates authoring from runtime dependencies.

Adoption accepts current paths and objects only; retired layouts, producer-era objects and old runtime formats are not migrated, parsed or re-authorized. Card bytes remain unchanged; curated review uses the separate CLI-only `stamp_cards.py --acknowledge-curated-review`.

```text
python3 Tools/adopt_standards.py --help
python3 Tools/adopt_standards.py . --plan <root-relative-plan.yaml> \
  --upstream-root <local-cambium-git-root> --upstream-ref <git-ref>
```

## Runtime workflow

Confirm task, scope and component choices first, then inspect the responsible writer's dry run before applying.

The main runtime entry points are:

- [`init_state.py`](init_state.py): atomically publish one confirmed Task Plan as an empty Queue, complete Task Contract, planning-only Coverage, and retained transaction Receipt;
- [`compile_queue.py`](compile_queue.py): materialize Required Queue state;
- [`run_task.py`](run_task.py): resolve one current, identity-bound action and advance deterministic Tool calls to the next Agent, user, Host, repair, or terminal boundary;
- [`check_queue.py`](check_queue.py): validate state and report the next resumable boundary;
- [`update_task.py`](update_task.py) and [`update_queue.py`](update_queue.py): perform their named controlled transitions;
- [`publish_delta.py`](publish_delta.py): validate and publish an Agent-complete candidate Delta for the current open batch;
- [`apply_delta.py`](apply_delta.py): preflight or apply one canonical runtime Delta from `--root` plus its repository-relative Delta path; Coverage is derived from the runtime contract and is not a caller-selected input;
- [`check_proof.py`](check_proof.py): verify the terminal proof object and its bound state when invoked in root mode.

Queue compilation preserves declared targets; `queued -> open` materializes current Coverage for that batch only. Unopened batches remain planning-only: their pages are not reset, projected, or treated as reviewed. Task Plans do not supply runtime `authoring_status`, `gate_receipts`, or `property_state`.

Use the live interfaces:

```text
python3 Tools/init_state.py --help
python3 Tools/run_task.py . --run-until-boundary
python3 Tools/apply_delta.py --help
python3 Tools/check_queue.py . --resume-status
```

Runtime data belongs in `.cambium/`, not `Tools/`. [`runtime_paths.py`](execution/task_runtime/runtime_paths.py) owns shared paths. Policy references `runtime_path_id`; the CLI compiler resolves its value and rejects unknown IDs, mismatched constraints or duplicate literal authorities.

### Audit evidence hand-off

[`audit_evidence_runtime`](execution/audit/audit_evidence_runtime.py) resolves complete attempt sets; supplying one ID cannot hide conflicts. Evidence-kind owners validate bindings under [K12/19](<../kernel/K12 Quality Assurance/19 Incremental Audit Planning.md>). `evidence_observation` shares facts and stage resolution within one read-only action, never across writes. Writers retain fresh locked checks, CAS and read-back.

Producers share `ReceiptPublication.locked_append` mechanics and `audit_receipt_contract` projections, not semantic authority.

For an open batch, create its AuditPlan and invoke the producer named by each due obligation:

```text
python3 Tools/prepare_audit_plan.py --help
python3 Tools/complete_audit_receipt.py --help
```

Ready obligations may be grouped with repeated `--obligation-id` (paired `--evidence-receipt` for finalization). Existing producers preserve evidence kinds, recheck inputs and serialize `--apply` writes. Batch Review requires pre-merge closure.

`publish_delta` assembles omitted page `gate_receipts`; invalid explicit references fail. See [runtime policy](agent-interface-policy.yaml).

## Generated interfaces

[`metadata_execution_contract.py`](governance/control/metadata_execution_contract.py) projects Kernel metadata and installed capabilities independently of the invocation chain. CLI parsers and `agent-interface-policy.yaml` feed:

`CLI → compiled CLI contract → MCP projection → Host configuration`

The target fixes storage: `source-distribution` owns `Tools/compiled/`; `carried-runtime` may write only:

- `.cambium/derived/interfaces/cli-contract.yaml`;
- `.cambium/derived/interfaces/mcp-tools.json`.

Targets cannot relocate these artifacts. Host configuration stays outside `.cambium`; the server accepts only a registered distribution or carried projection.

Check the tracked products without rewriting them:

```text
python3 Tools/metadata_execution_contract.py --root . --check
python3 Tools/compile_cli_contract.py . --check
python3 Tools/render_interface_projection.py . --check
python3 Tools/render_host_configs.py . --check
```

Build or verify the carried-runtime projections without changing distributed component bytes:

```text
python3 Tools/compile_cli_contract.py . --projection-target carried-runtime
python3 Tools/render_interface_projection.py . --projection-target carried-runtime
python3 Tools/render_host_configs.py . --projection-target carried-runtime --output-dir /absolute/adopter/.host-config-staging --distribution-root /absolute/adopter --workspace-root /absolute/adopter
```

Use `--help` and `--sources` before regenerating or installing a host product. [`mcp_server.py`](mcp_server.py) preserves the child tool's structured result and exit code; it makes no new governance judgment.

Each tool binds one reusable `output_contracts` declaration: always JSON, mode-selected JSON, or text. Compiler and MCP project that binding. Empty success requires an explicit mode allowance; `--json` alone proves nothing.

## Results and evidence

Each CLI's `--help` states its write mode, output options, and required inputs. Where supported:

- `--json` changes presentation, not the verdict;
- `--receipts` appends the tool's structured evidence at the declared adopter path;
- omitting `--apply` produces a dry-run plan;
- `--apply` authorizes only the transaction named by that tool.

Gate identity, receipt meaning, reuse, and completion authority remain with [K00/12](<../kernel/K00 Standards Control/12 Control Registry.md>) and [K12/07](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>). A SHA-256 value binds bytes; it is not a signature. Actor and reviewer fields are recorded assertions unless an external authenticated runner supplies a stronger trust anchor. Do not collapse a documented HOLD exit into either success or failure; callers must preserve the tool's exact result.

Audit producers return publication facts separately from their business verdict. A confirmed `changes-required` review is successfully recorded but is not passing review evidence. A write error can coexist with observed bytes; an uncertain result is not a claim that nothing was written. Manual-attestation tools return the same publication envelope in JSON mode, with their original record array under `receipts`. The transient envelope is not a Receipt and does not authorize a stage transition; catalogs still read and validate the persisted records.

MCP retains the raw `exit_code` and its process-code `verdict`, alongside `output_reliable` and `invocation_reliable`. Output validation or capability confirmation failure stops the call without discarding returned publication facts. Runner children use the same path admission, with separate acknowledgement scopes and no widening of matching inherited capabilities. Child execution and subsequent next-action observation remain separate results.

Runner awaits expose a generated `required_input` object schema and its `x-cambium-binding`. Fill only the exposed properties; batch, plan, obligation, phase and machine-selected evidence remain bound by the Tool. Parameter shapes come from the actual CLI declaration, while review conditions come from the existing domain contract. External-resolution awaits have `required_input: null`: perform the named external work and ask for a new action, rather than submitting a readiness assertion.

Omission, explicit `null`, and an empty list are distinct. Only an explicitly nullable CLI argument may encode `null` by omission. For `record_batch_page_review`, omitting `consumed_evidence_ref` requests owner-derived references, while `[]` asserts an exactly empty reference set; the shared argv renderer preserves both. Inputs that cannot be represented are rejected, never silently widened to a default scope.

An execution response identifies the requested action, any dispatched substeps, and a failure stage. Pre-dispatch rejection has no child return code. A later failure retains earlier substep output and publication observations; `next_action_error` does not erase those results or authorize an automatic writer retry. These observations last only for the call and do not create another runtime log or Receipt.

The compiler derives each tool's Host-environment boundary from its actual entrypoint wrapper. MCP and Runner use the same output observer: a declared Host handoff retains its diagnostic and any prior output, requires a stop, and does not claim either a passing Receipt or that no write occurred.

Receipt-specific observation reads the effective append after-image, not a cached input snapshot. Component-owned receipt targets remain internal, rooted by the invocation descriptor rather than exposed as extra public arguments. This covers receipt file reads and writes and their reachable catalog targets; it is not a claim that every runtime directory enumeration, multi-object transaction or Host filesystem operation is descriptor-based. Their existing owners retain their locks, hashes, CAS and completion checks.

Two input roles may reference the same retained snapshot. Their canonical path, target and parent identities must agree before physical read authority can be shared; the read acknowledges those equivalent path capabilities, not the roles' governance meaning. Write capabilities are not coalesced, and same-mode write aliases remain refused.

### Correcting an erroneous evidence declaration

Use [`record_evidence_invalidation.py`](record_evidence_invalidation.py) (also MCP) with the K12/07 decision. See `--help` for exact subjects, authority bindings and event identity; preview before `--apply`, and retry the same identity/payload. The append-only event neither passes review nor rolls back state. Refresh runtime, then follow the original producer or permitted transition; L rounds remain retained, not restarted.

## Receipt-sealing maintenance runbook

Use `seal_receipts.py --apply` only in an exclusive quiet window after a resume check, a dry run, and a verified restorable copy of `.cambium/`. After interruption, apply `--reconcile` only when its preview proves the exact plan safe; otherwise restore the copy. Re-prove history and resumability before releasing the window:

```text
python3 Tools/seal_receipts.py . --verify
python3 Tools/check_queue.py . --resume-status
```

## Tool engineering checks

Module-boundary facts and reports are Tool engineering artifacts, not Kernel rules. Inspect or regenerate the report through its own interface:

```text
python3 Tools/module_boundary_report.py --root . --emit-manifest
```

[`TOOL_CATALOG.md`](TOOL_CATALOG.md) and `compiled/tool-catalog.json` join module boundaries, taxonomy, interface policy, operation capabilities and source facts, distinguishing imports, registrations and transports:

```text
python3 Tools/generate_tool_catalog.py .
python3 Tools/generate_tool_catalog.py . --check
```

Generation writes both views; `--check` recomputes and compares bytes without writing.

[`test-ownership.yaml`](test-ownership.yaml) owns classification; [`TEST_CATALOG.md`](TEST_CATALOG.md) adds source/fixture facts. Build/MCP retains the full E2E; maintenance uses a validated closed checkpoint:

```text
python3 Tools/generate_test_catalog.py .
python3 Tools/generate_test_catalog.py . --check
```

The catalog runner separates test levels. Each selected file runs once; files whose cases are all `parallel_safe` may run concurrently, while isolation-sensitive files remain serial. `full` includes all retained levels without repeating mixed-level files:

```text
make fast
make integration
make e2e
make slow
make full
```

Run the focused README contract tests with:

```text
python3 -m unittest Tools.tests.test_tools_readme_inventory
```

When adding or changing a public CLI:

1. make its `argparse` declaration the only invocation source;
2. classify the public arguments in `agent-interface-policy.yaml`;
3. register a single implementation owner in the relevant machine registry;
4. update `module-boundaries.yaml` if the dependency direction changes;
5. regenerate the affected products under `compiled/`;
6. add focused tests for the observable result and failure modes.

The repository license is [Apache-2.0](../LICENSE.md).
