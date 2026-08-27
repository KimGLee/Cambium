# Cambium Licensing

Cambium uses scoped licensing: each Cambium-maintained, tracked file in the
official distribution is governed by the license assigned below. The two
licenses are not alternatives for the same material.

## Apache License 2.0 — software and implementation materials

Copyright 2026 KimGLee

The Apache License, Version 2.0 applies to the following Cambium-maintained
files in the official distribution:

- Files tracked under `Tools/**`, including scripts, schemas, and tool
  documentation, except adopter-generated artifacts described below.
- Files tracked under `.github/**`, plus `Makefile` and
  `distribution-boundary.yaml`, as repository engineering and distribution
  control materials.
- `.gitignore`.
- `NOTICE`.
- Future executable software, runtime adapters, or implementation files only
  when they are explicitly assigned to Apache-2.0.

The complete license text is in
[`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt). The Apache-licensed
portion also carries the notice in [`NOTICE`](NOTICE).

## Creative Commons Attribution 4.0 — standards and documentation

Licensed material: Cambium standards and profile materials

Copyright 2026 KimGLee

The Creative Commons Attribution 4.0 International license (CC BY 4.0) applies
to the following Cambium-maintained files in the official distribution:

- Files tracked under `kernel/**`.
- Files tracked under `Card/**` and `Read Set/**`.
- Files tracked under `profiles/**`, except adopter-created profile content
  described below.
- Files tracked under `assets/readme/**`.
- `README.md` and `README.zh-CN.md`.
- `ROADMAP.md` and `ROADMAP.zh-CN.md`.
- `CONTRIBUTING.md`.
- `LICENSE.md` and `ATTRIBUTION.md`.

The complete legal code is in
[`LICENSES/CC-BY-4.0.txt`](LICENSES/CC-BY-4.0.txt). Attribution information
and a reusable attribution form are in
[`ATTRIBUTION.md`](ATTRIBUTION.md).

CC BY 4.0 permits sharing and adaptation, including commercial use, subject to
its terms. In particular, when licensed or adapted material is shared, the
license requires appropriate attribution, retention of the specified notices
where applicable, and an indication of modifications.

## Adopter-Generated Material

File location alone does not transfer ownership or apply a Cambium license to
material created by an adopter. In particular:

- Generated vocabulary files such as `.cambium/derived/vocab.yaml`, receipts under
  `.cambium/receipts/**`, runtime evidence, and similar instance outputs are not
  licensed by Cambium merely because Cambium generated them or they live in an
  adopter runtime namespace.
- An adopter's original profile answers are not licensed by Cambium merely
  because the profile is stored under `profiles/`. Any portions copied or
  adapted from Cambium's `_template` remain subject to CC BY 4.0; the license
  does not require the adopter to apply CC BY 4.0 to their independent added
  material.

Cambium-originated material reproduced in a generated artifact retains its
applicable license. Adopter-originated values, answers, and evidence do not
become Apache-2.0 or CC BY 4.0 merely because of the artifact's output path.

## License Administration Files

This scope statement, the license copies under `LICENSES/`, `NOTICE`, and
`ATTRIBUTION.md` document the licensing arrangement. The verbatim legal texts
under `LICENSES/` are reproduced as legal instruments and are not assigned a
Cambium project license. None of these files replaces or modifies either
license's legal terms.

Any future Cambium-maintained file outside the scopes listed above must be
explicitly assigned a license here or by an SPDX license identifier before it
is released. No license for otherwise unlisted material is implied by
proximity to licensed material.

## Relicensing Record

Material moved between the two scopes above is recorded here, because the file
paths alone no longer show which license the material was released under
before the move. A same-scope machine-contract relocation may also be recorded
for ownership traceability; such an entry is identified as not relicensing.

- 2026-08-06 — The closed membership registry of profile-overridable execution
  defaults and constitutional constants (the `overridable` and
  `constitutional` blocks) moved from
  `Tools/schemas/execution_defaults.template.yaml`, released under
  Apache-2.0, to `kernel/K00 Standards Control/execution-defaults-base.yaml`,
  released under CC BY 4.0. Both scopes are Cambium-maintained and
  copyright 2026 KimGLee, so the move required no third-party permission; the
  earlier Apache-2.0 release of that material is not withdrawn by it. The
  remaining blocks of the original file stay Apache-2.0 under `Tools/**`.
- 2026-08-27 — The Kernel leaf-size policy, approved-exception rationales, and
  follow-up record moved from
  `kernel/K00 Standards Control/16 Leaf Module Size Register.md`, released
  under CC BY 4.0, to `Tools/kernel-size-policy.yaml` and
  `Tools/kernel-size-exceptions.md`, released under Apache-2.0. The earlier
  CC BY 4.0 release of that material is not withdrawn.
- 2026-08-27 — The exceptable-policy identities, owner references, quota
  defaults, limit domains, and effective-policy fingerprint payload moved from
  `Tools/contract_exception_policy.py`, released under Apache-2.0, to
  `kernel/K00 Standards Control/contract-exception-policy-base.yaml`, released
  under CC BY 4.0. The earlier Apache-2.0 release of that material is not
  withdrawn.
- 2026-08-27 — Runtime Ledger identities and fingerprint fields; Queue and
  task state identities, classes, holds, execution modes, and transition
  catalogs; Guidance and Amendment status/finality values; completion-control
  states; and operational Amendment operation identities moved from
  `Tools/queue_runtime/canon.py`, `Tools/kblib.py`, `Tools/update_task.py`,
  `Tools/queue_runtime/task_record.py`, `Tools/queue_runtime/task_progress.py`,
  `Tools/register_amendment.py`, `Tools/apply_amendment.py`, and
  `Tools/queue_runtime/amendments.py`, released under Apache-2.0, to
  `kernel/K13 Task Runtime and Execution Control/runtime-state-model.json`,
  released under CC BY 4.0. The earlier Apache-2.0 release of that material is
  not withdrawn.
- 2026-08-27 — The common Profile slot set, extension-table contract, and
  Profile-specific closed interface values moved from `Tools/profile_contract.py`,
  released under Apache-2.0, to
  `kernel/K00 Standards Control/profile-interface.yaml`, released under CC BY
  4.0. The earlier Apache-2.0 release of that material is not withdrawn; the
  Tool now only loads and validates the Kernel-owned interface.
- 2026-08-27 — The base receipt-dimension identities, evidence-role
  identities, and extension-target mappings moved from
  `Tools/profile_contract.py` and, for the repeated base-dimension tuple,
  `Tools/check_proof.py`, released under Apache-2.0, to
  `kernel/K12 Quality Assurance/audit-dimension-base.yaml`, released under CC
  BY 4.0. The earlier Apache-2.0 release of that material is not withdrawn;
  Tool consumers now load and validate the K12-owned registry.
- 2026-08-27 — The machine-readable Batch-close Closed List member identities
  and ordering moved from `Tools/queue_runtime/close_gate.py`, released under
  Apache-2.0, to
  `kernel/K12 Quality Assurance/batch-close-closed-list.yaml`, released under
  CC BY 4.0. The earlier Apache-2.0 release of that material is not withdrawn;
  K12/09 remains the semantic and boundary explanation while the Tool now only
  loads and projects the Kernel-owned registry.
- 2026-08-27 — Shared Coverage top-level, page, batch-spec, and reroute field
  shapes; Work Spec binding fields; and Coverage Delta/control field shapes
  moved from `Tools/queue_runtime/runtime.py`,
  `Tools/queue_runtime/coverage.py`, `Tools/queue_runtime/work_spec.py`,
  `Tools/queue_runtime/delta.py`, `Tools/amendment_policy.py`,
  `Tools/compile_queue.py`, and `Tools/apply_delta.py` to
  `Tools/coverage_contract.py` and `Tools/work_spec_contract.py`. All source
  and destination files remain Apache-2.0 under `Tools/**`; this is an
  implementation-ownership relocation, not relicensing.
- 2026-08-27 — The Corpus Planning Profile-slot envelope and applicability
  branches, artifact-role and semantic-acceptance identities, pass-receipt
  freshness binding, path/SHA currentness classes, and close-trigger
  identities moved from `Tools/check_profile.py`,
  `Tools/check_corpus_plan.py`, and `Tools/queue_runtime/close_gate.py`,
  released under Apache-2.0, to
  `kernel/K02 Knowledge Work Construction/corpus-planning-contract.yaml`,
  released under CC BY 4.0. The earlier Apache-2.0 release of that material is
  not withdrawn; the Tool now only validates and projects the K02-owned
  machine contract.
- 2026-08-27 — Card path-prefix, generated-index, document-type, and
  generation-mode identities moved from repeated literals in
  `Tools/stamp_cards.py` and `Tools/card_activation.py`, released under
  Apache-2.0, to `Card/card.schema.yaml`, released under CC BY 4.0. Read Set
  path-prefix, generated-index, and phase-field identities likewise moved
  from repeated Tool literals to `Read Set/read-set.schema.yaml`, released
  under CC BY 4.0. The earlier Apache-2.0 release of those identities is not
  withdrawn; Tool consumers now load the two component-owned projections.
- 2026-08-27 — The serialized Card layout, discriminator, generation mode,
  field list, section list, and identifier shapes moved from
  `Card/card.schema.yaml`, released under CC BY 4.0, to
  `Tools/schemas/card.schema.yaml`, released under Apache-2.0. This corrects
  machine-contract ownership without changing the Card checklist semantics or
  withdrawing the earlier CC BY 4.0 release. The independent Card size budget
  remains under `Card/card-budget.yaml`; the Read Set contract remains under
  `Read Set/read-set.schema.yaml`.
- 2026-08-27 — The shipped `profiles/` namespace and its reserved
  non-candidate member set moved from duplicate declarations in
  `Tools/scaffold_profile.py` and `Tools/profile_onboarding_status.py` to
  `Tools/profile_layout_contract.py`. All source and destination files remain
  Apache-2.0 under `Tools/**`; this is an implementation-ownership
  relocation, not relicensing.
- 2026-08-27 — The ordered priority identities and volatility review-interval
  values formerly repeated in `Tools/freshness_engine.py` and
  `Tools/compile_queue.py`, released under Apache-2.0, were consolidated into
  the existing owner
  `kernel/K08 Metadata and Status/vocabulary-base.yaml`, released under CC BY
  4.0. The earlier Apache-2.0 release of those repeated values is not
  withdrawn; Tool consumers now share one strict read-only projection.
- 2026-08-27 — Metadata value shapes, source-adapter owner-record fields, and
  the legacy property-state field/status/record shape were consolidated from
  repeated declarations in `Tools/project_page_state.py` and
  `Tools/queue_runtime/property_state.py` into
  `Tools/metadata_execution_contract.py` and
  `Tools/metadata_property_state.py`. All source and destination files remain
  Apache-2.0 under `Tools/**`; this is an implementation-ownership relocation,
  not relicensing.
