# Tools: deterministic execution for Cambium

`Tools/` contains the programs that check, calculate, transform, generate, and
write Cambium data in deterministic, repeatable, and testable ways. This
README explains how to find and run those programs. It is not a second copy of
the governance rules, state contracts, Card checklists, or Read Set loading
declarations.

All shipped scripts use the Python 3 standard library. Cambium's supported
restricted-YAML parsing and rendering goes through [`kblib.py`](kblib.py).

## Responsibility boundary

Tools own implementation: algorithms, command-line interfaces, validation,
controlled writes, generated projections, structured diagnostics, and the
observable result guarantees promised by an implemented capability.

Tools do not decide whether knowledge is deep, accurate, clear, valuable, or
approved. They do not create a governance rule, select a Profile, choose a
task route, author a Card, define a Read Set, or turn an asserted actor name
into authenticated identity.

| Component | Owns | How Tools may interact with it |
|---|---|---|
| [`kernel/`](../kernel/) | Common governance rules and implementation-independent contracts | Validate or execute a named rule without restating it here |
| [`profiles/`](../profiles/) | One knowledge base's confirmed custom requirements | Validate confirmed values and consume stable bindings |
| [`Card/`](../Card/) | Curated, short action checklists | Check structure/currentness and deliver the selected projection |
| [`Read Set/`](<../Read Set/>) | Static loading relationships | Parse and resolve declared loading edges |
| `.cambium/` | One adopter's current state, bound inputs, evidence, recovery material, transient work, and derived projections | Read or change registered objects through the responsible checker or writer |
| [`Tools/`](./) | Deterministic implementation and Tool-owned machine contracts | Provide the program, diagnostics, and verifiable result |

A checker observes and reports; it does not repair the object while checking.
A writer changes only the transaction named by its interface and uses an
explicit write mode such as `--apply`. A zero process exit is not, by itself,
proof of the resulting state: critical writers perform the read-back required
by their external contract.

## Canonical navigation

The following files are the maintained entry points. Follow them instead of
copying their tables or field lists into prose.

| Concern | Canonical or machine-readable entry point | Tool consumer or producer |
|---|---|---|
| Common Gate identities, receipt selectors, producer positions, and revalidation projection | [K00/12 Control Registry](<../kernel/K00 Standards Control/12 Control Registry.md>) and [`control-registry.yaml`](<../kernel/K00 Standards Control/control-registry.yaml>) | [`control_registry_contract.py`](control_registry_contract.py) parses the shared machine contract; [`queue_runtime/gate_registry.py`](queue_runtime/gate_registry.py), [`run_gates.py`](run_gates.py), and the registered producer consume it |
| Profile extension interface | [Profile Extension Interface](<../kernel/K00 Standards Control/19 Profile Extension Interface.md>) and [`profile-interface.yaml`](<../kernel/K00 Standards Control/profile-interface.yaml>) | [`profile_contract.py`](profile_contract.py), [`profile_admission.py`](profile_admission.py), [`check_profile.py`](check_profile.py) |
| Corpus Planning slot envelope, applicability branches, receipt freshness binding, and close triggers | [K02 Corpus Planning](<../kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md>) and [`corpus-planning-contract.yaml`](<../kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml>) | [`corpus_planning_contract.py`](corpus_planning_contract.py) projects the shared contract for [`check_profile.py`](check_profile.py), [`check_corpus_plan.py`](check_corpus_plan.py), and receipt producers/consumers |
| Base audit dimensions, evidence roles, and Profile extension-target mappings | [K12 audit evidence semantics](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>) and [`audit-dimension-base.yaml`](<../kernel/K12 Quality Assurance/audit-dimension-base.yaml>) | [`audit_dimension_contract.py`](audit_dimension_contract.py), [`profile_contract.py`](profile_contract.py), [`check_proof.py`](check_proof.py), and Gate consumers |
| Exceptable policy identities, owner references, limit domains, defaults, and effective-policy payload | [`contract-exception-policy-base.yaml`](<../kernel/K00 Standards Control/contract-exception-policy-base.yaml>) | [`contract_exception_policy.py`](contract_exception_policy.py) loads, validates, resolves, and fingerprints the policy without owning it |
| Batch-close Closed List membership and order | [`batch-close-closed-list.yaml`](<../kernel/K12 Quality Assurance/batch-close-closed-list.yaml>) | [`batch_close_contract.py`](batch_close_contract.py) loads and validates the registry and projects its producer-era evidence fields |
| Installed Profile scan capabilities | [`scan-capabilities.yaml`](scan-capabilities.yaml) | [`profile_contract.py`](profile_contract.py) and registered scan adapters |
| Serialized Card layout, document discriminator, generation mode, and field shape | [`schemas/card.schema.yaml`](schemas/card.schema.yaml) | [`card_contract.py`](card_contract.py) is the sole engineering-schema loader; [`stamp_cards.py`](stamp_cards.py), [`card_activation.py`](card_activation.py), and interface tooling consume its projection without treating it as Card governance semantics |
| Independent Card size budget | [`Card/card-budget.yaml`](../Card/card-budget.yaml) | [`stamp_cards.py`](stamp_cards.py) enforces the Card-specific body and action-item ceilings |
| Read Set layout, generated-index name, phase fields, and declaration shape | [`Read Set/read-set.schema.yaml`](<../Read Set/read-set.schema.yaml>) | [`read_set_contract.py`](read_set_contract.py) loads and resolves the owner; Card, activation, proof, and Task Contract consumers read that projection |
| Producer-era Task Contract component-path migrations | [`schemas/component-path-migrations.yaml`](schemas/component-path-migrations.yaml) | [`queue_runtime/task_contract.py`](queue_runtime/task_contract.py) projects only a persisted Standards-adoption before-image; ordinary runtime and the proposed after-image remain strict |
| Shipped `profiles/` namespace layout and reserved non-candidate members | [`profile_layout_contract.py`](profile_layout_contract.py) | [`scaffold_profile.py`](scaffold_profile.py) and [`profile_onboarding_status.py`](profile_onboarding_status.py) |
| Tool capability implementation ownership | [`operation-capabilities.yaml`](operation-capabilities.yaml) | [`metadata_execution_contract.py`](metadata_execution_contract.py) and capability consumers |
| K08 priority ordering and volatility review intervals | [`vocabulary-base.yaml`](<../kernel/K08 Metadata and Status/vocabulary-base.yaml>) | [`vocabulary_contract.py`](vocabulary_contract.py) strictly projects the owner values for [`freshness_engine.py`](freshness_engine.py), [`check_freshness.py`](check_freshness.py), and [`compile_queue.py`](compile_queue.py) |
| Metadata value/source-adapter record shapes and legacy property-state shape | [`metadata_execution_contract.py`](metadata_execution_contract.py) and [`metadata_property_state.py`](metadata_property_state.py) | [`project_page_state.py`](project_page_state.py) and [`queue_runtime/property_state.py`](queue_runtime/property_state.py) consume the owner projections without restating their members |
| Runtime Ledger identities, state classes, transition catalogs, and control-status closed sets | [`runtime-state-model.json`](<../kernel/K13 Task Runtime and Execution Control/runtime-state-model.json>) | [`runtime_state_contract.py`](runtime_state_contract.py) and runtime writers/checkers |
| Shared Coverage, Work Spec binding, and Coverage Delta field shapes | [`coverage_contract.py`](coverage_contract.py) and [`work_spec_contract.py`](work_spec_contract.py) | Runtime validators, [`amendment_policy.py`](amendment_policy.py), [`compile_queue.py`](compile_queue.py), and Amendment/Delta apply/check paths |
| Public CLI and agent interface policy | [`agent-interface-policy.yaml`](agent-interface-policy.yaml) | [`compile_cli_contract.py`](compile_cli_contract.py) resolves runtime `runtime_path_id` references through [`runtime_paths.py`](runtime_paths.py); [`render_interface_projection.py`](render_interface_projection.py) consumes the compiled result |
| Adopter runtime path spelling, lifecycle class, and policy path-reference projection | [`runtime_paths.py`](runtime_paths.py) | Runtime producers, consumers, and the CLI-contract compiler |
| Tool and package dependency direction | [`module-boundaries.yaml`](module-boundaries.yaml) | [`module_boundary_facts.py`](module_boundary_facts.py), [`module_boundary_report.py`](module_boundary_report.py), boundary tests |
| Kernel leaf-size implementation policy | [`kernel-size-policy.yaml`](kernel-size-policy.yaml) and [`kernel-size-exceptions.md`](kernel-size-exceptions.md) | [`check_kernel_size.py`](check_kernel_size.py) |
| Host adapter observations | [`host-conformance.yaml`](host-conformance.yaml) | Host conformance tests and interface generation |
| Input templates | [`schemas/`](schemas/) | The checker or writer named by each workflow |

Files under [`compiled/`](compiled/) are generated projections of declared
inputs. They can be checked or regenerated, but they do not acquire semantic
authority from being generated. The CLI parser in each entry-point script is
the source for its invocation shape; use `--help` for the current options.

Support libraries are intentionally not repeated in an exhaustive prose
inventory. Their ownership and permitted dependency direction are checked from
source and `module-boundaries.yaml`.

## Quick verification

List the adopter Gate sweep without executing it, then run it:

```text
python3 Tools/run_gates.py . --list
python3 Tools/run_gates.py .
```

Card currentness and Kernel size are independent repository-engineering Tool
preflights, not Kernel Gates:

```text
python3 Tools/stamp_cards.py . --check
python3 Tools/check_kernel_size.py .
```

`stamp_cards.py --check` verifies the serialized-Card engineering schema, the
Card-owned size budget, source bindings, curated-review bindings, Card/Read Set
pairing, and generated navigation. It does not prove that a summary is
semantically correct or that an Agent understood it.

`kernel-size-policy.yaml` is the sole numeric owner of Kernel leaf-size limits
and registered measurements. `check_kernel_size.py` separates a hard failure
(exit `1`) from an otherwise safe result that still needs engineering review
(exit `2`).

## Profile candidate workflow

A Profile begins as a candidate proposed through user/Agent discussion. The
Tool can scaffold and mechanically validate it; confirmation and adoption stay
with the user or designated authority.

Preview the candidate creation, apply it only after reviewing the plan, then
validate the resulting candidate:

```text
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
python3 Tools/check_profile.py profiles/my-profile --root .
```

The Profile template guide is [`profiles/README.md`](../profiles/README.md).
For initial or pre-runtime adoption, inspect the transaction interface before
supplying a confirmed plan:

```text
python3 Tools/apply_profile_adoption.py --help
python3 Tools/apply_profile_adoption.py . --plan <root-relative-plan.yaml>
```

Omitting `--apply` previews the transaction. A later Standards/Profile change
in an existing runtime uses `adopt_standards.py` and the adoption rules owned
by [K12/10](<../kernel/K12 Quality Assurance/10 Standards Version Adoption.md>),
not an improvised edit to Profile or `.cambium` files.

When a frozen Task Contract names a component path from a registered producer
era, `adopt_standards.py` may use that one-way registry only to validate the
persisted before-image against the exact current paths declared by the plan.
The original contract bytes remain the receipt/fingerprint authority, and the
after-image must pass ordinary runtime validation with no legacy alias.

The adoption writer may refresh an observed source hash, but it cannot approve
a curated Card summary. When it refuses a stale curated review, a human first
reviews the changed sources and Card body, then explicitly records that review
with `python3 Tools/stamp_cards.py . --acknowledge-curated-review` before
retrying adoption.

```text
python3 Tools/adopt_standards.py --help
```

## Runtime workflow

Do not infer task, scope, route, Card, Read Set, or Profile choices from this
README. Once those inputs have been confirmed, use the responsible dry-run
writer and inspect its plan before applying it.

The main runtime entry points are:

- [`init_state.py`](init_state.py): initialize an empty adopter task runtime
  from explicit inputs;
- [`apply_task_plan.py`](apply_task_plan.py): apply the confirmed initial task
  plan;
- [`compile_queue.py`](compile_queue.py): materialize Required Queue state;
- [`check_queue.py`](check_queue.py): validate state and report the next
  resumable boundary;
- [`update_task.py`](update_task.py), [`update_queue.py`](update_queue.py), and
  [`apply_delta.py`](apply_delta.py): perform their named controlled
  transitions;
- [`check_proof.py`](check_proof.py): verify the terminal proof object and its
  bound state when invoked in root mode.

Start from the live CLI contracts rather than copying a long example with
instance-specific values:

```text
python3 Tools/init_state.py --help
python3 Tools/apply_task_plan.py --help
python3 Tools/check_queue.py . --resume-status
```

Runtime data belongs under `.cambium/`; do not redirect current state or
runtime receipts into `Tools/`. Physical path spellings shared by producers
and consumers come from `runtime_paths.py`. Agent-interface policy stores the
same source identity as `runtime_path_id`; `compile_cli_contract.py` resolves
that ID to the physical `value` in its generated projection and rejects an
unknown ID, constraint mismatch, or a second literal runtime-path authority.

## Generated interfaces

The generation chain is:

1. `metadata_execution_contract.py` combines the Kernel metadata contract with
   installed operation capabilities.
2. `compile_cli_contract.py` projects each entry point's `argparse` interface
   together with `agent-interface-policy.yaml`.
3. `render_interface_projection.py` creates the agent-facing MCP projection.
4. `render_host_configs.py` creates host registration and workspace-binding
   products for a selected environment.

Check the tracked products without rewriting them:

```text
python3 Tools/metadata_execution_contract.py --root . --check
python3 Tools/compile_cli_contract.py . --check
python3 Tools/render_interface_projection.py . --check
python3 Tools/render_host_configs.py . --check
```

Use `--help` and `--sources` where available before regenerating or installing
a host product. [`mcp_server.py`](mcp_server.py) is launched by a rendered host
configuration; it preserves the child tool's structured result and exit code
instead of making a new governance judgment.

## Results and evidence

Each CLI's `--help` states its write mode, output options, and required inputs.
Where supported:

- `--json` changes presentation, not the verdict;
- `--receipts` appends the tool's structured evidence at the declared adopter
  path;
- omitting `--apply` produces a dry-run plan;
- `--apply` authorizes only the transaction named by that tool.

Gate identity, receipt meaning, reuse, and completion authority remain with
[K00/12](<../kernel/K00 Standards Control/12 Control Registry.md>) and
[K12/07](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>).
A SHA-256 value binds bytes; it is not a signature. Actor and reviewer fields
are recorded assertions unless an external authenticated runner supplies a
stronger trust anchor. Do not collapse a documented HOLD exit into either
success or failure; callers must preserve the tool's exact result.

## Receipt-sealing maintenance runbook

`seal_receipts.py --apply` removes frozen receipt bytes from the hot register,
so it is supported only in an exclusive quiet window. This is the one recovery
procedure that operators need in this README. The receipt semantics remain in
[K12/07](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>);
implementation details remain in the tool and its tests.

### Before applying

1. Confirm that no Cambium or adopter writer, checker, or receipt appender is
   running against the repository on any host or session.
2. Confirm that the runtime has no interrupted writer:

   ```text
   python3 Tools/check_queue.py . --resume-status
   ```

3. Preview the seal and verify the affected registers and counts:

   ```text
   python3 Tools/seal_receipts.py .
   ```

4. Take a restorable copy of `.cambium/` and record its hash before using
   `--apply`.

### After an interruption

1. Inspect the recoverable plan without writing:

   ```text
   python3 Tools/seal_receipts.py . --reconcile
   ```

2. If the report says the transaction is safely reconcilable, finish it:

   ```text
   python3 Tools/seal_receipts.py . --reconcile --apply
   ```

3. If reconciliation refuses because another owner is still active, wait for
   or safely resolve that process first. If it refuses because recovery
   evidence is missing or has changed, do not edit that evidence and do not
   retry blindly; restore the verified pre-seal `.cambium/` copy.
4. For any interruption the tool cannot reconcile, restore the pre-seal copy
   and restart the sealing procedure in a new quiet window.

### After applying

Re-prove the sealed history and then revalidate runtime resumability:

```text
python3 Tools/seal_receipts.py . --verify
python3 Tools/check_queue.py . --resume-status
```

Release the maintenance window only after both checks are clean.

## Tool engineering checks

Module-boundary facts and reports are Tool engineering artifacts, not Kernel
rules. Inspect or regenerate the report through its own interface:

```text
python3 Tools/module_boundary_report.py --root . --emit-manifest
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
