# Tools: deterministic execution for Cambium

`Tools/` contains Cambium's deterministic, repeatable, and testable programs. This README is navigation and operating guidance, not a copy of governance rules, state contracts, Cards, or Read Sets.

All shipped Python code uses the standard library. Cambium's supported restricted-YAML parsing and rendering goes through [`platform/common/kblib.py`](platform/common/kblib.py).

## Responsibility boundary

Tools own implementation: algorithms, command-line interfaces, validation, controlled writes, generated projections, structured diagnostics, and the observable result guarantees promised by an implemented capability.

Tools do not decide whether knowledge is deep, accurate, clear, valuable, or approved. They do not create a governance rule, select a Profile, choose a task route, author a Card, define a Read Set, or turn an asserted actor name into authenticated identity.

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

[`tool-taxonomy.yaml`](tool-taxonomy.yaml) owns the Area, Domain, and Layer vocabulary. [`module-boundaries.yaml`](module-boundaries.yaml) assigns every shipped implementation module to one `Area → Domain → Layer` and checks dependency direction. The paths below are navigation into that checked structure, not a second classification.

| Physical Area | Domains |
|---|---|
| [`governance/`](governance/) | `standards/`, `profile/`, `control/` |
| [`knowledge/`](knowledge/) | `structure/`, `metadata/`, `content/`, `rendering/` |
| [`execution/`](execution/) | `planning/`, `task_runtime/`, `audit/`, `evidence/`, `context_delivery/` |
| [`platform/`](platform/) | `agent_interface/`, `distribution/`, `repository/`, `common/` |

Top-level `Tools/<tool>.py` paths remain the stable public CLI surface and forward to their Area/Domain modules. Layer is a checked classification, not another directory level: `entrypoint`, `application`, `contract`, `infrastructure`, or `api`. Shared mechanics live under [`platform/common/`](platform/common/); task state lives under [`execution/task_runtime/`](execution/task_runtime/), including [`queue_runtime/`](execution/task_runtime/queue_runtime/).

Use `python3 Tools/module_boundary_report.py --format hierarchy` to view every shipped module as `Area / Domain / Layer / module`; that report and [`TOOL_CATALOG.md`](TOOL_CATALOG.md) are generated views, not additional owners. The Catalog describes the complete Cambium source distribution and is therefore distribution-only; an adopter carries the governed runtime subset instead of a stale copy of this source-tree projection.

## Canonical navigation

The following files are the maintained entry points. Follow them instead of copying their tables or field lists into prose.

| Concern | Canonical or machine-readable entry point | Tool consumer or producer |
|---|---|---|
| Common Gate identities, receipt selectors, producer positions, and revalidation projection | [K00/12 Control Registry](<../kernel/K00 Standards Control/12 Control Registry.md>) and [`control-registry.yaml`](<../kernel/K00 Standards Control/control-registry.yaml>) | [`control_registry_contract.py`](governance/control/control_registry_contract.py), [`queue_runtime/gate_registry.py`](execution/task_runtime/queue_runtime/gate_registry.py), [`run_gates.py`](run_gates.py), and registered producers |
| Profile extension interface | [Profile Extension Interface](<../kernel/K00 Standards Control/19 Profile Extension Interface.md>) and [`profile-interface.yaml`](<../kernel/K00 Standards Control/profile-interface.yaml>) | [`profile_contract.py`](governance/profile/profile_contract.py), [`profile_admission.py`](governance/profile/profile_admission.py), [`check_profile.py`](check_profile.py) |
| Corpus Planning slot envelope and close triggers | [K02 Corpus Planning](<../kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle.md>) and [`corpus-planning-contract.yaml`](<../kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml>) | [`corpus_planning_contract.py`](execution/planning/corpus_planning_contract.py), [`check_profile.py`](check_profile.py), [`check_corpus_plan.py`](check_corpus_plan.py) |
| Base audit dimensions, evidence roles, and Profile extension targets | [K12 audit evidence semantics](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>) and [`audit-dimension-base.yaml`](<../kernel/K12 Quality Assurance/audit-dimension-base.yaml>) | [`audit_dimension_contract.py`](execution/audit/audit_dimension_contract.py), [`profile_contract.py`](governance/profile/profile_contract.py), [`check_proof.py`](check_proof.py) |
| AuditPlan and full AuditReceipt contracts | [K12/19](<../kernel/K12 Quality Assurance/19 Incremental Audit Planning.md>), [`audit-plan-contract.yaml`](<../kernel/K12 Quality Assurance/audit-plan-contract.yaml>), [`audit-receipt-contract.yaml`](<../kernel/K12 Quality Assurance/audit-receipt-contract.yaml>) | [`audit_plan_contract.py`](execution/audit/audit_plan_contract.py), [`audit_receipt_contract.py`](execution/audit/audit_receipt_contract.py) |
| Substantive and Batch Review protocols | [K12/12](<../kernel/K12 Quality Assurance/12 Substantive Correctness Review.md>), [`substantive-review-contract.yaml`](<../kernel/K12 Quality Assurance/substantive-review-contract.yaml>), and [K12/14](<../kernel/K12 Quality Assurance/14 Batch Review.md>) | [`record_substantive_review.py`](record_substantive_review.py), [`complete_audit_receipt.py`](complete_audit_receipt.py), and [`record_batch_review.py`](record_batch_review.py) |
| Policy IDs, registration, limit domains, and effective payload | [`contract-exception-policy-base.yaml`](<../kernel/K00 Standards Control/contract-exception-policy-base.yaml>) | [`contract_exception_policy.py`](governance/control/contract_exception_policy.py) |
| Batch-close Closed List membership and order | [`batch-close-closed-list.yaml`](<../kernel/K12 Quality Assurance/batch-close-closed-list.yaml>) | [`batch_close_contract.py`](execution/audit/batch_close_contract.py) |
| Installed Profile scan capabilities | [`scan-capabilities.yaml`](scan-capabilities.yaml) | [`profile_contract.py`](governance/profile/profile_contract.py) and scan adapters |
| Serialized Card shape and generation mode | [`schemas/card.schema.yaml`](schemas/card.schema.yaml) | [`card_contract.py`](execution/context_delivery/card_contract.py), [`stamp_cards.py`](stamp_cards.py), [`card_activation.py`](execution/context_delivery/card_activation.py) |
| Independent Card size budget | [`Card/card-budget.yaml`](../Card/card-budget.yaml) | [`stamp_cards.py`](stamp_cards.py) enforces the Card-specific body and action-item ceilings |
| Read Set layout, generated index, and phase fields | [`Read Set/read-set.schema.yaml`](<../Read Set/read-set.schema.yaml>) | [`read_set_contract.py`](execution/context_delivery/read_set_contract.py) and its consumers |
| Shipped `profiles/` namespace layout | [`profile_layout_contract.py`](governance/profile/profile_layout_contract.py) | [`scaffold_profile.py`](scaffold_profile.py), [`profile_onboarding_status.py`](profile_onboarding_status.py) |
| Tool capability implementation ownership | [`operation-capabilities.yaml`](operation-capabilities.yaml) | [`metadata_execution_contract.py`](governance/control/metadata_execution_contract.py) and capability consumers |
| K08 priority order and review intervals | [`vocabulary-base.yaml`](<../kernel/K08 Metadata and Status/vocabulary-base.yaml>) | [`vocabulary_contract.py`](knowledge/metadata/vocabulary_contract.py), [`freshness_engine.py`](knowledge/metadata/freshness_engine.py), [`check_freshness.py`](check_freshness.py), [`compile_queue.py`](compile_queue.py) |
| Metadata and property-state record shapes | [`metadata_execution_contract.py`](governance/control/metadata_execution_contract.py), [`metadata_property_state.py`](knowledge/metadata/metadata_property_state.py) | [`project_page_state.py`](knowledge/metadata/project_page_state.py), [`queue_runtime/property_state.py`](execution/task_runtime/queue_runtime/property_state.py) |
| Runtime identities, state classes, and transitions | [`runtime-state-model.json`](<../kernel/K13 Task Runtime and Execution Control/runtime-state-model.json>) | [`runtime_state_contract.py`](execution/task_runtime/runtime_state_contract.py) and runtime tools |
| Coverage, Work Spec, and Coverage Delta shapes | [`coverage_contract.py`](execution/planning/coverage_contract.py), [`work_spec_contract.py`](execution/planning/work_spec_contract.py) | Runtime validators, [`amendment_policy.py`](execution/task_runtime/amendment_policy.py), [`compile_queue.py`](compile_queue.py) |
| Public CLI and agent interface policy | [`agent-interface-policy.yaml`](agent-interface-policy.yaml) | [`compile_cli_contract.py`](compile_cli_contract.py), [`runtime_paths.py`](execution/task_runtime/runtime_paths.py), [`render_interface_projection.py`](render_interface_projection.py) |
| Adopter runtime path spelling and lifecycle class | [`runtime_paths.py`](execution/task_runtime/runtime_paths.py) | Runtime tools and the CLI-contract compiler |
| Tool dependency direction | [`module-boundaries.yaml`](module-boundaries.yaml) | [`module_boundary_facts.py`](platform/distribution/module_boundary_facts.py), [`module_boundary_report.py`](module_boundary_report.py), boundary tests |
| Upstream identity and immutable component bytes | [`distribution-boundary.yaml`](../distribution-boundary.yaml) | [`upstream_identity.py`](platform/distribution/upstream_identity.py), [`upstream_component_boundary.py`](platform/distribution/upstream_component_boundary.py), [`check_upstream_components.py`](check_upstream_components.py) |
| Kernel leaf-size implementation policy | [`kernel-size-policy.yaml`](kernel-size-policy.yaml) and [`kernel-size-exceptions.md`](kernel-size-exceptions.md) | [`check_kernel_size.py`](check_kernel_size.py) |
| Host adapter observations | [`host-conformance.yaml`](host-conformance.yaml) | Host conformance tests and interface generation |
| Input templates | [`schemas/`](schemas/) | The checker or writer named by each workflow |

Files under [`compiled/`](compiled/) are generated, non-authoritative projections. Each entry point's parser owns its invocation shape; use `--help`. Support libraries are not repeated here because source and `module-boundaries.yaml` check their ownership and dependency direction.

## Quick verification

List the adopter Gate sweep without executing it, then run it:

```text
python3 Tools/run_gates.py . --list
python3 Tools/run_gates.py .
```

Verify adopter components against an upstream Git revision. The result records the resolved full SHA and applies that revision's `distribution-boundary.yaml`.

```text
python3 Tools/check_upstream_components.py <adopter-root> --upstream-root <cambium-git-root> --revision <git-ref> --check-manifest
```

Run it from a separately trusted upstream checkout. A clean `--write-manifest` writes only `.cambium/derived/upstream-component-byte-manifest.tsv`; unregistered executable artifacts fail.

Card currentness and Kernel size are independent repository-engineering Tool preflights, not Kernel Gates:

```text
python3 Tools/stamp_cards.py . --check
python3 Tools/check_kernel_size.py .
```

`stamp_cards.py --check` reads the Card path from its schema and checks budget, bindings, pairing, and navigation. It does not judge semantics or Agent understanding. Card bytes stay immutable and unbound to adopter Standards.

`kernel-size-policy.yaml` is the sole numeric owner of Kernel leaf-size limits and registered measurements. `check_kernel_size.py` separates a hard failure (exit `1`) from an otherwise safe result that still needs engineering review (exit `2`).

## Profile candidate workflow

A Profile begins as a candidate proposed through user/Agent discussion. The Tool can scaffold and mechanically validate it; confirmation and adoption stay with the user or designated authority.

Preview the candidate creation, apply it only after reviewing the plan, then validate the resulting candidate:

```text
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
python3 Tools/check_profile.py profiles/my-profile --root .
```

The Profile template guide is [`profiles/README.md`](../profiles/README.md). For initial or pre-runtime adoption, inspect the transaction interface before supplying a confirmed plan:

```text
python3 Tools/apply_profile_adoption.py --help
python3 Tools/apply_profile_adoption.py . --plan <root-relative-plan.yaml> \
  --upstream-root <local-cambium-git-root> --upstream-ref <git-ref>
```

Omitting `--apply` previews the transaction. A later Standards/Profile change in an existing runtime uses `adopt_standards.py` and the adoption rules owned by [K12/10](<../kernel/K12 Quality Assurance/10 Standards Version Adoption.md>), not an improvised edit to Profile or `.cambium` files.

Standards adoption accepts only component paths and objects defined by the current contract. Retired path layouts, producer-era objects, and old runtime formats remain outside Cambium's runtime space; they are not migrated, parsed, or re-authorized. Adoption writers never modify Card bytes. Curated Card review remains the separate, CLI-only `stamp_cards.py --acknowledge-curated-review` operation.

```text
python3 Tools/adopt_standards.py --help
python3 Tools/adopt_standards.py . --plan <root-relative-plan.yaml> \
  --upstream-root <local-cambium-git-root> --upstream-ref <git-ref>
```

## Runtime workflow

Do not infer task, scope, route, Card, Read Set, or Profile choices from this README. Once those inputs have been confirmed, use the responsible dry-run writer and inspect its plan before applying it.

The main runtime entry points are:

- [`init_state.py`](init_state.py): atomically publish one confirmed Task Plan as an empty Queue, complete Task Contract, planning-only Coverage, and retained transaction Receipt;
- [`compile_queue.py`](compile_queue.py): materialize Required Queue state;
- [`run_task.py`](run_task.py): resolve one current, identity-bound action and advance deterministic Tool calls to the next Agent, user, Host, repair, or terminal boundary;
- [`check_queue.py`](check_queue.py): validate state and report the next resumable boundary;
- [`update_task.py`](update_task.py) and [`update_queue.py`](update_queue.py): perform their named controlled transitions;
- [`publish_delta.py`](publish_delta.py): validate and publish an Agent-complete candidate Delta for the current open batch;
- [`apply_delta.py`](apply_delta.py): preflight or apply one canonical runtime Delta from `--root` plus its repository-relative Delta path; Coverage is derived from the runtime contract and is not a caller-selected input;
- [`check_proof.py`](check_proof.py): verify the terminal proof object and its bound state when invoked in root mode.

Task Plan schema v3 removes the former skeleton-state SHA copy and deliberately omits `authoring_status`, `gate_receipts`, and `property_state`. Queue compilation preserves all declared targets, while the first `queued -> open` transition materializes current Coverage for that batch's manifest only. Unopened batches remain planning-only and their knowledge pages are not reset, projected, or treated as currently reviewed.

Start from the live CLI contracts rather than copying a long example with instance-specific values:

```text
python3 Tools/init_state.py --help
python3 Tools/run_task.py . --run-until-boundary
python3 Tools/apply_delta.py --help
python3 Tools/check_queue.py . --resume-status
```

Runtime data belongs under `.cambium/`; do not redirect current state or runtime receipts into `Tools/`. Physical path spellings shared by producers and consumers come from [`execution/task_runtime/runtime_paths.py`](execution/task_runtime/runtime_paths.py). Agent-interface policy stores the same source identity as `runtime_path_id`; `compile_cli_contract.py` resolves that ID to the physical `value` in its generated projection and rejects an unknown ID, constraint mismatch, or a second literal runtime-path authority.

For an open batch, create its AuditPlan and invoke the producer named by each due obligation:

```text
python3 Tools/prepare_audit_plan.py --help
python3 Tools/record_substantive_review.py --help
python3 Tools/record_batch_page_review.py --help
python3 Tools/record_batch_judgment.py --help
python3 Tools/record_changed_scope_evidence.py --help
python3 Tools/record_rendering_verification.py --help
python3 Tools/complete_audit_receipt.py --help
python3 Tools/record_batch_review.py --help
```

Substantive, changed-scope, and rendering producers may emit precursors. Use `complete_audit_receipt` only for obligations requiring a full AuditReceipt; other evidence keeps its kind. Run `record_batch_review` after pre-merge closure. Writes require `--apply`.

[`agent-interface-policy.yaml`](agent-interface-policy.yaml) constrains runtime paths. Page and target select AuditPlan identities; they grant no read access.

## Generated interfaces

There are two independent generation paths. [`governance/control/metadata_execution_contract.py`](governance/control/metadata_execution_contract.py) combines the Kernel metadata contract with installed operation capabilities; it is not an invocation-interface stage. Separately, each CLI parser plus `agent-interface-policy.yaml` produces the CLI contract, which produces the MCP projection, which in turn produces Host registration and workspace bindings:

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

## Results and evidence

Each CLI's `--help` states its write mode, output options, and required inputs. Where supported:

- `--json` changes presentation, not the verdict;
- `--receipts` appends the tool's structured evidence at the declared adopter path;
- omitting `--apply` produces a dry-run plan;
- `--apply` authorizes only the transaction named by that tool.

Gate identity, receipt meaning, reuse, and completion authority remain with [K00/12](<../kernel/K00 Standards Control/12 Control Registry.md>) and [K12/07](<../kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation.md>). A SHA-256 value binds bytes; it is not a signature. Actor and reviewer fields are recorded assertions unless an external authenticated runner supplies a stronger trust anchor. Do not collapse a documented HOLD exit into either success or failure; callers must preserve the tool's exact result.

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

[`TOOL_CATALOG.md`](TOOL_CATALOG.md) and `compiled/tool-catalog.json` are generated navigation views over `module-boundaries.yaml`, `tool-taxonomy.yaml`, `agent-interface-policy.yaml`, `operation-capabilities.yaml`, and source facts. They keep static imports, registered relationships, and transport declarations separate:

```text
python3 Tools/generate_tool_catalog.py .
python3 Tools/generate_tool_catalog.py . --check
```

The first command regenerates both projections. `--check` recomputes both from the same sources and compares them byte for byte without writing.

[`test-ownership.yaml`](test-ownership.yaml) is the single reviewed source for test ownership, execution level, lifecycle, and mixed-module method overrides. [`TEST_CATALOG.md`](TEST_CATALOG.md) and `compiled/test-catalog.json` join that source with test and fixture facts observed from the repository; they are generated navigation and runner inputs, not a second test contract:

```text
python3 Tools/generate_test_catalog.py .
python3 Tools/generate_test_catalog.py . --check
```

The catalog-owned runner keeps fast contract feedback separate from isolated integration, representative end-to-end, and real security/concurrency/recovery tests. Every selected test file runs in exactly one child process. Files whose selected cases are all marked `parallel_safe` may run with bounded file-level concurrency; isolation-sensitive files remain serial. `full` selects every retained level in one file-level pass, so mixed-level modules are not imported or rebuilt more than once:

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
