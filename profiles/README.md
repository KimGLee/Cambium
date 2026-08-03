# Profiles

## Creating A Profile

`profiles/_template/` is a guided, domain-neutral form. Copy it to `profiles/<profile-id>/`, replace every `TODO(profile)` placeholder, keep or update the manifest bindings when files move, and run `python3 Tools/check_profile.py profiles/<profile-id>`. Headings, row or field labels, and YAML comments around a placeholder describe the expected answer shape; they are guidance, not additional values. Use a lowercase path slug matching `[a-z0-9][a-z0-9_-]*`; the manifest `profile_id` must equal the directory name. Fill identity and the core slots before registries so later entries reference existing IDs and paths rather than restating their rules. The template itself is neither runnable nor a default profile.

Use these declarations consistently:

- `Required`: supply a value.
- `Optional`: write `None` or `Configured`; a configured table must contain at least one row.
- `Conditional`: write `Not applicable — <reason>` or `Configured`; a configured table must contain the required rows.
- References between slots use IDs, paths, or owner pointers. Do not copy the referenced rule into the referring slot.

## Profile Loading Contract

The effective standard is `kernel + one selected profile`. The kernel references stable slot names; the selected profile's manifest binds those slots to concrete files. A task that needs an unresolved slot must stop rather than claim the composed standard is loaded.

Kernel Runtime Cards belong to `kernel/`. Profiles share the kernel route registry; they do not mirror kernel routes as profile slots, and each task loads only the applicable routes. R11 reads the existing `Profile Scope` together with task-time contract and ledger state. R12 reads existing judgment items, scans, and gates; an ordinary targeted audit needs no profile registration. A profile may only add namespaced supplemental routes or gates through `Routing And Gate Registry`; it cannot replace, shadow, or disable a kernel route or Card.

## Profile Scope Slot

**Required.** Provide the knowledge-base goal and audience, ordered content-priority factors, excluded scope, logical layers and directories, organizing mainline / Knowledge Spine, placement-role bindings, new-page placement order, terminology structure, foundation-depth predicates, production-reasoning applicability, representative sample types, and dependency-ordered build stages. New-page placement is first-match and ends in a catch-all row. An unused layer role binds to `None` plus a fallback Layer ID; an unused expression predicate is `always false`. Representative samples and build stages may be `Not applicable` only when the profile does not support the corresponding bulk or module work. This slot supplies the standing Excluded Scope; R11 records the actual per-task Required / optional / deferred / excluded boundaries in the Task Contract and Coverage Ledger rather than adding another profile table. This slot cannot override kernel conservation, ownership, migration, or quality rules.

## Priority Rubric Slot

**Required.** Provide testable P0 and P1 grant predicates and the reader capability or time horizon each grant protects. P2 remains the kernel fallback for other in-scope pages. Quota selections belong only to `Execution Default Overrides`; this slot cannot redefine P0/P1/P2, tier derivation, quota coupling, or exemptions.

## Execution Default Overrides Contract

**Required in the manifest.** Unlisted items use their kernel defaults; the table contains only explicit overrides. `Tools/schemas/execution_defaults.template.yaml#overridable` owns the closed set of allowed item names and points to each value's kernel owner. Duplicate, unknown, default-restating, and constitutional rows are invalid.

## Vocabulary Extensions Slot

**Required file; extensions are conditional.** Register each domain once in `volatility_defaults`; the composer derives the domain vocabulary from those keys. Register optional additions to other kernel-extensible fields and optional profile-owned fields. The composer reads the profile ID from the sibling manifest, derives each base-field extension owner from the extensions-file path, and adds profile-only controlled fields to the generated frontmatter-field list. An expression-readiness axis, when present, is a profile-owned field with a field name, values, `Expression Status Axis` role, and one prose owner. Extensions cannot delete, rename, or redefine kernel values. `Tools/vocab.yaml` is generated and is not a rule owner.

## Language Contract Slot

**Required.** Provide body and secondary-language handling, reader-facing display forms for kernel-protected identities, naming syntax for folders/pages/terms/assets, aliases, headings and labels, abbreviation and display order, file-name annotation boundaries, and the content-length unit. Domain-scoped additions or exceptions to K10/04 anti-patterns and stricter formatting-migration invalidation are optional and reference the stable kernel IDs; the profile does not restate the kernel defaults. It may interpret kernel soft lengths in words or characters but cannot change their numeric ranges or make length a hard gate.

## Expression Layer Entry Slot

**Required file; artifact registration is optional.** Each configured artifact declares its ID, type, display label, entry point, single profile-rule owner, canonical dependency map, invalidation trigger, and either a readiness-field/supplemental-gate reference or `None`. No registered artifact means the profile supplies no concrete R05 target; it does not remove R05.

## Source Policy Slot

**Required.** Register concrete source authority and what each source is canonical for, verification entry points and pins/windows, and staleness triggers with bounded affected scope. Domain-specific comparison rules and provenance additions are optional and may only tighten the kernel policy; kernel conflict, gap, `unknown`, `contested`, provenance, and promotion behavior are not restated here.

## Role Registry Slot

**Required.** Bind `proposer`, `gatekeeper`, `executor`, `stopper`, `knowledge-host`, and `knowledge-host UI`. Metric-traceability bindings for task, dataset, trial, execution runtime, grader, and aggregation are conditional on reporting evaluated metrics. Additional profile roles are optional. Role bindings identify actors or systems; verifier commands and gate predicates belong to their own registries.

## Audit Dimension Registry Slot

**Required file.** Register every profile-owned predicate consumed by audit as one judgment item with an item ID, receipt dimension, audit layer, audit object, evidence role, and single predicate owner. Start with Foundation Depth and every acceptance item referenced by a configured scan, specialized audit invariant, or gate. One item is one condition that can independently pass or fail; conditions that always share one verdict and owner remain one item. Point to the predicate owner rather than copying its rule. Descriptive policy, dispatch maps, and staleness triggers are not judgment items unless a gate or receipt consumes their own verdict. An extension dimension supplies only an ID, its target list(s), and its meaning; pass/fail logic remains in judgment items. Registrations append to kernel dimensions and cannot redefine them or duplicate another predicate owner.

## Registered Scan Registry Slot

**Required.** Bind a deterministic residual-content verifier to `K12/09 item 6`, including its scope, verifier, candidate boundary, and an Acceptance Judgment Item ID from Audit Dimension Registry. It must satisfy the kernel single-vault-wide-run and ≤60-second limit. Additional profile candidate scans are optional. Review judges candidates but cannot replace execution of the required scan.

## Routing And Gate Registry Slot

**Required file; all registrations are optional unless another configured feature depends on one.** Supplemental routes declare a `P:<profile_id>:<route_name>` ID, the Rxx route supplemented, and a resolvable profile Read Set. A profile Read Set is Markdown with frontmatter `type: profile-read-set`, its profile `route_id`, and `supplements: Rxx`, followed by `Purpose`, `Start`, `Triggered`, and `Gate` sections; it loads alongside the named kernel route. The registry may also append justified L-tier triggers, cross-batch Specialized Audit invariants, and extension gates. A Specialized Audit row uses its Acceptance Judgment Item ID as the invariant identity and adds only applicability / trigger, verification procedure, and receipt-reuse boundary; the referenced judgment item remains the sole registration of the predicate's receipt dimension, audit layer, audit object, evidence role, and predicate-owner path. Ordinary targeted R12 audits require no row here. A configured readiness axis requires a gate that names its readiness field, completion values, Acceptance Judgment Item ID, and pass-authority Role ID. Each gate points to the kernel gate/owner it supplements; authority IDs reference Role Registry, readiness fields reference Vocabulary Extensions, and acceptance items reference Audit Dimension Registry. Nothing in this slot may replace a kernel route/Card, choose an ordinary-page default tier, lower a kernel-derived tier, or redefine S/M/L derivation.
