# Profiles

## Creating A Profile

`profiles/_template/` is a static, domain-neutral form. Copy it to `profiles/<profile-id>/`, replace every `TODO(profile)` placeholder, keep or update the manifest bindings when files move inside that profile folder, and run `python3 Tools/check_profile.py profiles/<profile-id>`. Every profile-owned slot must resolve inside the selected profile folder; a manifest cannot borrow another profile's files or a repository-root fallback. Headings, row or field labels, and YAML comments around a placeholder describe the expected answer shape; they are guidance, not additional values. Use a lowercase path slug matching `[a-z0-9][a-z0-9_-]*`; the manifest `profile_id` must equal the directory name. Fill identity and the core slots before registries so later entries reference existing IDs and paths rather than restating their rules. The template itself is neither runnable nor a default profile.

```text
cp -R profiles/_template profiles/my-profile
# Fill profiles/my-profile/, then:
python3 Tools/check_profile.py profiles/my-profile
```

Profile setup is currently manual and file-based. `check_profile.py` is the
canonical producer of the `profile-load` Gate: it validates a filled copy and
derives its Profile dependency closure, but does not ask questions, generate
domain decisions, author the profile, approve it, or select it for use.

Use these declarations consistently:

- `Required`: supply a value.
- `Optional`: write `None` or `Configured`; a configured table must contain at least one row.
- `Conditional`: write `Not applicable — <reason>` or `Configured`; a configured table must contain the required rows.
- Write these declaration words bare, exactly as `_template` shows them (`- Registration: Configured`). The backticks above are this page's own code formatting; `check_profile.py` compares the literal cell text, so `` `Configured` `` with backticks is a different string and is rejected as `declaration-invalid`. The same applies to `None` and to the em dash in `Not applicable — <reason>`.
- References between slots use IDs, paths, or owner pointers. Do not copy the referenced rule into the referring slot.

## Fill Depth

`profiles/_template/` is the one form. Fill depth is a property of the
interview, not of a second directory: the template pre-closes every slot
switch that has a legal exit state, pre-fills the operational answers that
generalize, and leaves open only the decisions no template can make, while
`interview.yaml`'s `expansion_packs` walk those closed switches in the same
sitting for an operator who wants every one answered now. Both routes produce
fully conformant profiles — the difference is how many answers ship
pre-closed, never compliance.

A closed switch opens later through ordinary Standards adoption without
interrupting an active task, and the shapes for each closed branch travel as
comments in the slot file that closes it, so opening one needs no second
document. Nothing about shipping a switch closed weakens a gate or bypasses
R09. The template's `README.md`, and `interview.yaml` and `answer-patterns.md`
at this level, are orientation an assisting agent uses to conduct the fill;
the README is deleted from the copied profile and none of the three is ever
profile policy. Identity is unfilled, so the template is never runnable or
selectable in place.

```text
cp -R profiles/_template profiles/my-profile
rm profiles/my-profile/README.md   # template orientation, never profile policy
# Answer the open decisions (the template README lists them), then:
python3 Tools/check_profile.py profiles/my-profile
```

## Adoption Flow

The flow below holds at either fill depth, and
[interview.yaml](interview.yaml) carries it in machine-readable form for an
assisting agent (to answer every switch now, the interview also walks every
expansion pack instead of leaving it closed). A solo fill follows the same
steps by hand.

1. **Locate the corpus first.** Name the corpus directory, or accept a
   proposed default; create it when it does not exist. A profile describes a
   corpus, so no other answer is meaningful before this one. Environment
   setup time (creating, connecting, or granting the directory) is setup, not
   filling effort.
2. **Fill** — by interview or by hand — and validate with
   `check_profile.py`.
3. **Close with a review.** Before calling the fill done, enumerate every
   switch left in its exit state and every derived fill, confirm each still
   holds, open anything the operator wants opened now, and ask for any need
   the fill did not cover. A closed switch whose reason no longer holds is an
   unconfirmed answer, not a default.
4. **Adopt through R09.** Filling and checking never select the profile.

**Profile prose language.** Slot prose is written in this interface's
language (English) regardless of the corpus body language, so any agent or
reviewer can load any profile. Corpus-real literals — scan matchers, mandated
headings, display forms, aliases — keep the language of the content they
match and are marked as literals, never translated. This is an authoring and
review convention, not a checked gate; existing profiles align through
ordinary revision rather than a migration campaign.

## Profile Loading Contract

The effective standard is `kernel + one selected profile`. The exact manifest path recorded as `selected_profile_manifest` in the active Standards state is the sole selection; a directory's existence, its `profile_id`, a generated vocabulary header, or discovery order does not select it. Multiple filled profiles may coexist, but exactly one is active. After filling and checking a copied profile, adopt it through R09 governance before content work; changing the active selection is a Standards revision and bumps `standards_version`. The kernel references stable slot names, and that manifest binds them to concrete files. A task that needs an unresolved slot must stop rather than claim the composed standard is loaded.

Loadability is a transitive package property, not only a manifest check. The
`profile-load` Gate derives one typed dependency closure from the exact
manifest: the manifest and fourteen file-bound slots, every predicate-owner path
and optional heading in `Audit Dimension Registry`, and every explicit
`--config` target in the required K12/09 residual-scan command. Every
manifest slot uses one exact canonical Profile-relative path; its typed edge
is normalized to the canonical repository-relative path. Transitive
Profile-owned references use canonical repository-relative spelling. Every
edge resolves as a safe, singly-linked, non-symlinked strict-UTF-8 file inside
that same Profile directory, and no closure member may retain the unfilled
sentinel regardless of filename suffix. `inline`, `./`, `..`, backslashes,
case or Unicode aliases, extension guessing, another Profile, a repository-root
fallback, or an absolute path is not part of the package and fails loading
even when the target bytes exist. A predicate-owner fragment must identify
exactly one Markdown heading.

The closure is derived in memory and has no second authored manifest. A
persistent verifier under `Tools/` is governed executable code, not a
Profile-owned dependency; corpus pages and the externally bound Corpus
Planning artifacts keep their own resolution contracts. Profile dependency
members likewise do not enter a task's `selected_read_sets` or
`loaded_module_paths`. Batch close consumes the same resolved Profile contract
before executing its residual scan: `profile-load` proves package authority
and resolvability, while `registered-residual-content` proves what the admitted
scan found in corpus bytes. Neither result substitutes for the other.

The interface below defines **14 file-bound slots** — each an H2 heading ending in ` Slot`, each bound to one file by the manifest — plus one manifest-resident `Execution Default Overrides Contract`, which is a declaration table inside `profile.md` and never a bound file. A filled profile therefore has 15 manifest sections but only 14 slot bindings; `check_profile.py` reports `slots=14` and checks the overrides table separately.

Kernel Runtime Cards belong to `kernel/`. Profiles share the kernel route registry; they do not mirror kernel routes as profile slots, and each task loads only the applicable routes. R11 reads the existing `Profile Scope` together with task-time contract and ledger state. R12 reads existing judgment items, scans, and gates; an ordinary targeted audit needs no profile registration. A profile may only add namespaced supplemental routes or gates through `Routing And Gate Registry`; it cannot replace, shadow, or disable a kernel route or Card.

## Profile Scope Slot

**Required.** Provide the knowledge-base goal and audience, ordered content-priority factors, excluded scope, logical layers and directories, organizing mainline / Knowledge Spine, placement-role bindings, new-page placement order, terminology structure, foundation-depth predicates, production-reasoning applicability, representative sample types, and dependency-ordered build stages. [[kernel/K01 Scope and Architecture/01 Scope Boundaries|K01/01]] owns the boundaries, hierarchy, and directory responsibilities this slot answers for; its `Profile Scope Interface` section is the kernel side of this projection. New-page placement is first-match and ends in a catch-all row. An unused layer role binds to `None` plus a fallback Layer ID; an unused expression predicate is `always false`. Representative samples and build stages may be `Not applicable` only when the profile does not support the corresponding bulk or module work. This slot supplies the standing Excluded Scope; R11 records the actual per-task Required / optional / deferred / excluded boundaries in the Task Contract and Coverage Ledger rather than adding another profile table. This slot cannot override kernel conservation, ownership, migration, or quality rules.

A logical layer with multiple directories uses a semicolon-delimited list. Each value is the exact repository-relative directory path without a trailing slash; the checker treats display-only forms such as `Domain/` as a different, invalid machine path. Profile Scope is the sole owner of Layer IDs, directory sets, and layer responsibilities; the Global Map references those IDs instead of asking the adopter to repeat the same declarations.

## Corpus Planning Slot

**Conditional.** Large-scale corpus construction, corpus migration, and persistent multi-batch work MUST configure this slot; a bounded small task may select `not-applicable` with a nonempty reason only when it neither needs nor changes corpus-wide planning artifacts. Two gates read that choice and they read it at different moments: [[kernel/K00 Standards Control/13 Runtime Admission and Recovery|K00/13]] requires `configured` to admit large-scale work, and batch close requires it when the task selected R13 or the batch's manifest touches a bound planning artifact — an unrelated batch acquires no gate merely because the repository holds a plan. A corpus with no canonical owner yet cannot configure this slot at all, and K00/13 admits large-scale work only against a configured plan; [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|K02/03]] records that admission-ordering gap. The slot is one closed restricted-YAML document named by the manifest. Its exact top-level fields are `schema_version`, `applicability`, `artifact_bindings`, `capability_scale`, and `pass_authority`. `applicability` contains exactly `state` and `reason`; `artifact_bindings` contains exactly `global_map`, `capability_matrix`, and `gap_register`; every ordered scale item contains exactly `rank`, `value`, `predicate`, and `target_eligible`; `pass_authority` contains exactly `role_id` and `decision_scope_id`. `configured` requires a null reason, three distinct repository-relative YAML paths, a nonempty scale, and a complete pass authority. `not-applicable` requires a nonempty reason, three null bindings, an empty scale, and two null authority values. Additional fields are invalid. [[kernel/K02 Knowledge Work Construction/03 Corpus Planning Applicability and Lifecycle|K02/03]] owns applicability and lifecycle; [[kernel/K02 Knowledge Work Construction/04 Corpus Planning Runtime Audit and Gate Boundaries|K02/04]] owns runtime and gate boundaries; [[kernel/K02 Knowledge Work Construction/05 Global Map Contract|K02/05]], [[kernel/K02 Knowledge Work Construction/06 Capability Matrix Contract|K02/06]], and [[kernel/K02 Knowledge Work Construction/07 Gap Register Contract|K02/07]] own the three artifact contracts. The slot does not own Coverage disposition, Queue order or lifecycle, Progress task state, AuditPlans, receipts, revisions, fingerprints, or completion claims. A promoted Gap row records its Coverage handoff; Coverage and, only for unfinished Required work, the Required Queue become the canonical execution owners. Ordinary R12 targeted review needs no extra profile registration and does not become a corpus-planning pass.

Capability Scale rows carry an explicit integer `Rank`, contiguous from `0` and ordered lowest to highest. The checker compares Matrix current and target values by this rank; prose wording or row discovery order never supplies a hidden ordering.

## Structure Registry Slot

**Required file; unit and support-layer registration is conditional.** The slot is one closed restricted-YAML document named by the manifest, owned in semantics by [[kernel/K01 Scope and Architecture/05 Structural Unit Interface|K01/05]] and [[kernel/K01 Scope and Architecture/06 Support Layer Structural Interfaces|K01/06]]; `profiles/_template/structure-registry.yaml` carries the exact closed field shapes. Its exact top-level fields are `schema_version`, `applicability`, `units`, and `support_layers`. `applicability` contains exactly `state` and `reason`. `configured` requires a null reason and at least one unit; `not-applicable` requires a nonempty reason and empty `units` and `support_layers` — a profile whose corpus has no registered structural units (a flat notes corpus, a bounded one-off task) selects `not-applicable` rather than inventing hollow units. Each unit binds identity, kind, parent, root, entry, Global Map entry, and one explicit implementation mode per declared role; each support layer binds the shared base and its role-specific `bindings` block. Additional fields are invalid. `check_profile.py` validates the closed shape; `Tools/check_structure.py` is the `structure-registry` gate and resolves the declarations against the adopting repository. This slot cannot redefine Layer IDs (Profile Scope owns them), cannot carry completion, batch, hold, receipt, or statistics state, and cannot make an expression artifact a canonical owner.

## Metadata Contract Slot

**Required file; differences and extensions are conditional.** The slot is one closed restricted-YAML document named by the manifest; `profiles/_template/metadata-contract.yaml` carries the exact closed shapes. Its exact required top-level fields are `schema_version`, `applicability`, `applicability_differences`, `extension_fields`, `relationship_extensions`, and `section_roles`; `applicability` contains exactly `state`. One optional top-level key, `boundary_projection`, carries a `labels` mapping that overrides the K08/09 boundary-projection display labels (display text only — never schema or semantics; kernel English defaults apply when absent). `kernel-defaults` requires all four lists empty; `configured` requires at least one entry across them. `section_roles` carries the Language Contract's machine-readable display titles and bounded migration aliases for the K07 `sources` and K09 `related` section roles; the kernel defaults live in `kernel/K07 Sources and Accuracy/sources-role-base.yaml`, and the Language Contract prose remains the display-form owner. Kernel field modes are owned by [[kernel/K08 Metadata and Status/06 Frontmatter Applicability Contract|K08/06]] via `applicability-base.yaml`, writer and projection authority by [[kernel/K08 Metadata and Status/07 Frontmatter Writer and Projection Authority|K08/07]], kernel relationship fields by [[kernel/K08 Metadata and Status/08 Relationship Metadata Contract|K08/08]] via `relationship-base.yaml`, and the `boundary` block's schema, cross-page rules, and projection by [[kernel/K08 Metadata and Status/09 Page Boundary Contract|K08/09]] (checked by the advisory `boundary-contract` gate `Tools/check_boundary_contract.py`, rendered by `Tools/render_boundary_projection.py`; concern vocabularies, when a profile closes them, use the ordinary Vocabulary Extensions mechanism). A difference may only tighten a kernel mode; an extension field or relationship must carry its own mode, shape, prose owner, and — for relationships — direction and target, and cannot be a spelling variant or alias of a kernel field. `check_profile.py` validates the closed shape; `Tools/compose_page_contract.py` composes the effective contract into `Tools/page_contract.yaml`, and `Tools/check_page_contract.py` applies it in advisory mode. This slot cannot loosen a kernel `required`, `forbidden`, or safety/evidence condition, redefine mode words, or restate kernel defaults.

## Priority Rubric Slot

**Required.** Provide testable P0 and P1 grant predicates and the reader capability or time horizon each grant protects. P2 remains the kernel fallback for other in-scope pages. [[kernel/K00 Standards Control/07 Effort Tiering and Priority Quota|K00/07]] owns tier derivation and the quota model and delegates the P0/P1 grant conditions here. Quota selections belong only to `Execution Default Overrides`; this slot cannot redefine P0/P1/P2, tier derivation, quota coupling, or exemptions.

## Execution Default Overrides Contract

**Required in the manifest.** Unlisted items use their kernel defaults; the table contains only explicit overrides. `kernel/K00 Standards Control/execution-defaults-base.yaml#overridable` owns the closed set of allowed item names and points to each value's kernel owner; `kernel/K00 Standards Control/09 Default Constraints Snapshot.md` registers that file, and the constants a profile may never override are the `constitutional` block of the same registry. Duplicate, unknown, default-restating, and constitutional rows are invalid.

## Vocabulary Extensions Slot

**Required file; extensions are conditional.** Register each domain once in `volatility_defaults`; the composer derives the domain vocabulary from those keys. Register optional additions to other kernel-extensible fields and optional profile-owned fields. [[kernel/K08 Metadata and Status/01 Frontmatter and Core Vocabularies|K08/01]] owns the frontmatter schema and the core vocabularies these extensions append to. The composer reads the profile ID and this slot's path from the selected manifest, derives each base-field extension owner from the resolved extensions-file path, and adds profile-only controlled fields to the generated frontmatter-field list. An expression-readiness axis, when present, is a profile-owned field with a field name, values, `Expression Status Axis` role, and one prose owner. Extensions cannot delete, rename, or redefine kernel values. `Tools/vocab.yaml` is generated and is not a rule owner.

## Language Contract Slot

**Required.** Provide body and secondary-language handling, reader-facing display forms for kernel-protected identities, naming syntax for folders/pages/terms/assets, aliases, headings and labels, abbreviation and display order, file-name annotation boundaries, and the content-length unit. Domain-scoped additions or exceptions to K10/04 anti-patterns and stricter formatting-migration invalidation are optional and reference the stable kernel IDs; the profile does not restate the kernel defaults. It may interpret kernel soft lengths in words or characters but cannot change their numeric ranges or make length a hard gate.

## Expression Layer Entry Slot

**Required file; artifact registration is optional.** Each configured artifact declares its ID, type, display label, entry point, single profile-rule owner, canonical dependency map, invalidation trigger, and either a readiness-field/supplemental-gate reference or `None`. No registered artifact means the profile supplies no concrete R05 target; it does not remove R05. [[kernel/K11 Expression Layer/01 Expression Architecture and Separation|K11/01]] owns expression separation and names this slot as the registry its artifacts come from.

## Source Policy Slot

**Required.** Register concrete source authority and what each source is canonical for, verification entry points and pins/windows, and staleness triggers with bounded affected scope. [[kernel/K07 Sources and Accuracy/01 Source Hierarchy and Evidence Roles|K07/01]] owns the source hierarchy, evidence roles, verification, and freshness model this slot instantiates. Domain-specific comparison rules and provenance additions are optional and may only tighten the kernel policy; kernel conflict, gap, `unknown`, `contested`, provenance, and promotion behavior are not restated here.

## Role Registry Slot

**Required.** Bind `proposer`, `gatekeeper`, `executor`, `stopper`, `knowledge-host`, and `knowledge-host UI`. Metric-traceability bindings for task, dataset, trial, execution runtime, grader, and aggregation are conditional on reporting evaluated metrics. Additional profile roles are optional. Role bindings identify actors or systems; verifier commands and gate predicates belong to their own registries. [[kernel/K04 Content Depth/03 Process and Flow Structure|K04/03]] defines the role vocabulary bound here.

## Audit Dimension Registry Slot

**Required file.** Register every profile-owned predicate consumed by audit as one judgment item with an item ID, receipt dimension, audit layer, audit object, evidence role, and single predicate owner. Start with Foundation Depth and every acceptance item referenced by a configured scan, specialized audit invariant, or gate. One item is one condition that can independently pass or fail; conditions that always share one verdict and owner remain one item. Point to the predicate owner rather than copying its rule. Every owner path is a Profile dependency and therefore remains inside this Profile; an optional `#heading` must resolve exactly once in the named Markdown file. Descriptive policy, dispatch maps, and staleness triggers are not judgment items unless a gate or receipt consumes their own verdict. An extension dimension supplies only an ID, its target list(s), and its meaning; pass/fail logic remains in judgment items. Registrations append to kernel dimensions and cannot redefine them or duplicate another predicate owner.

The `Extension Dimensions` block is machine-enumerable even when no extension exists. It contains exactly one bare `- Registration: None` or `- Registration: Configured` declaration and exactly one table headed `Dimension ID`, `Target list(s): review, receipt, or review + receipt`, and `Meaning`. `None` carries no data row; `Configured` carries at least one complete row. A Dimension ID is unique `lower_snake_case`, begins with a letter, and cannot collide with a kernel base dimension. The target list is exactly `review`, `receipt`, or `review + receipt`. Profile validation rejects an absent, duplicated, contradictory, or unreadable block; Terminal Proof consumes the same registration and accounts for every dimension whose target list includes `receipt`.

The evidence role is exactly one of `emits`, `consumes`, or `triggers`, and the three differ in what the run leaves behind. `emits`: this item is the producer of a receipt for its own audit object. `consumes`: the verdict is already proved by a receipt produced elsewhere for the same snapshot, so review records that reused receipt ID rather than re-deriving the verdict and does not open a second receipt for the same audit object ([[kernel/K12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|K12/07]] owns that reuse boundary). `triggers`: the item raises review candidates only — it produces no receipt of its own and cannot fail a gate by itself; the disposition belongs to the review that consumes those candidates.

## Registered Scan Registry Slot

**Required.** Bind a deterministic residual-content verifier to `K12/09 item 6`, including its scope, verifier, candidate boundary, and an Acceptance Judgment Item ID from Audit Dimension Registry. It must satisfy the kernel single-vault-wide-run and ≤60-second limit. The registration also supplies executable positive controls for every required structure form the verifier claims to detect, and the verifier must prove that each control classifies as a candidate through its production classifier. The command MUST implement the shared `--positive-controls-only` invocation without changing its other arguments: batch close runs that mode first and the registered production command second, then requires their final summaries to match on the K12/09 binding fields. The control-input representation remains verifier-specific and need not use headings. The profile owns the registration, machine configuration, predicate, positive-control declaration, and judgment binding; an explicit `--config` target is therefore a Profile dependency and must resolve inside this Profile. A persistent executable shipped by Cambium belongs to `Tools/`, not inside the profile. When exact frontmatter and heading matching is sufficient, use `Tools/check_residual_content.py` with a profile-owned copy of [the residual scan config template](../Tools/schemas/residual_scan_config.template.yaml); its `mandated_headings` field is that verifier's concrete positive-control list. A custom verifier that declares no `--config` remains legal; the checker does not guess that arbitrary flags such as `--rules` name Profile dependencies. Additional profile candidate scans are optional. Review judges candidates but cannot replace execution of the required scan.

## Escalation Policy Slot

**Required file; all registrations are optional.** Register every condition under which this instance's executor MUST suspend the task and hand the decision to a person, beyond the kernel trigger that already obliges explicit user authorization to modify the Standards or the selected profile. [[kernel/K13 Task Runtime and Execution Control/17 Escalation Policy|K13/17]] owns the escalation contract and that kernel trigger; this slot registers the instance's additions and cannot weaken or restate the kernel one. Each registration declares a `lower_snake_case` Trigger ID unique within the profile, the condition that fires it marked exactly `machine-checkable` or `review-checkable`, a deciding Role ID from `Role Registry` (usually `stopper`), and the resume condition that counts as the decision having been made. Trigger IDs are bare slugs in their own namespace: they are neither routes nor gates and take no `P:` prefix. A trigger is not a gate — it emits no receipt, blocks no transition, and no checker fires on it; `check_profile.py` validates this registration's shape, and whether a fired trigger was honored is a review question. Registering nothing is a complete answer for a bounded task whose only stop condition is the kernel trigger, and is written as an explicit `None` rather than left empty. What happens on a fired trigger — `active -> paused` through the sole task-state writer with resume information saved — belongs to [[kernel/K13 Task Runtime and Execution Control/03 Task State and Transition Rules|K13/03]] and is not restated here.

## Routing And Gate Registry Slot

**Required file; all registrations are optional unless another configured feature depends on one.** Supplemental routes declare a `P:<profile_id>:<route_name>` ID, the Rxx route supplemented, and a resolvable profile Read Set. Supplemental routes, profile Read Sets, and extension gates share that one `P:` namespace: [[kernel/K00 Standards Control/01 Operating Role and Reading Protocol|K00/01]] grants the same `P:<profile_id>:<route_name>` form to all three and owns it. One consequence is worth stating plainly: a supplemental route and an extension gate that reuse the same final segment collide on one ID. Kernel gate IDs are bare slugs carrying no `P:` prefix, so a profile registration is always distinguishable from a kernel one. No checker parses this registry, so a within-profile collision is visible only to review. A profile Read Set is Markdown with frontmatter `type: profile-read-set`, its profile `route_id`, and `supplements: Rxx`, followed by `Purpose`, `Start`, `Triggered`, and `Gate` sections; it loads alongside the named kernel route. The registry may also append justified L-tier triggers, cross-batch Specialized Audit invariants, and extension gates. A Specialized Audit row uses its Acceptance Judgment Item ID as the invariant identity and adds only applicability / trigger, verification procedure, and receipt-reuse boundary; the referenced judgment item remains the sole registration of the predicate's receipt dimension, audit layer, audit object, evidence role, and predicate-owner path. Ordinary targeted R12 audits require no row here. A configured readiness axis requires a gate that names its readiness field, completion values, Acceptance Judgment Item ID, and pass-authority Role ID. Each gate points to the kernel gate/owner it supplements; authority IDs reference Role Registry, readiness fields reference Vocabulary Extensions, and acceptance items reference Audit Dimension Registry. Nothing in this slot may replace a kernel route/Card, choose an ordinary-page default tier, lower a kernel-derived tier, or redefine S/M/L derivation.
