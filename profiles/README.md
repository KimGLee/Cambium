# Profile

A Profile is the set of customized governance requirements that a user has chosen and confirmed for one knowledge repository. It binds the extension points opened by the Kernel; it does not restate or weaken Kernel rules.

The common semantic interface is [K00/19](<../kernel/K00 Standards Control/19 Profile Extension Interface.md>) and its [`profile-interface.yaml`](<../kernel/K00 Standards Control/profile-interface.yaml>) registry. Each domain keeps its own slot meaning and legal values; K00 composes these contracts without taking over their ownership. Tools own [`profile-encoding.yaml`](../Tools/governance/profile/profile-encoding.yaml): TOML encoding, physical source mapping, and evaluation assembly. This README, the interview, the template, and rendered views are guidance, not additional semantic authorities.

The single answer entry point is `profiles/<profile-id>/profile.toml`, containing `schema_version`, `profile_id`, and `slots` keyed by stable slot IDs. Values use semantic snake_case field names and real numbers, booleans, lists, and objects—not Markdown table headings. Independent policy bodies or scan configuration may be referenced where needed; their content is not copied into a second owner. TOML has no null value: omitted bindings are meaningful only in the branches defined by their owner. A missing configured binding is not silently converted into an inactive choice.

Kernel CUE contracts check semantic objects and legal values without requiring a TOML document wrapper. The Tool-owned encoding map supplies the root `schema_version`, `slots` container, and `#Profile` / `#ProfileDraft` evaluation entry points through a generated [`profile-document.cue`](../Tools/governance/profile/profile-document.cue) projection. Directory-safe Profile identity and identity/path equality are Tool layout checks, not repeated Kernel rules. Where a domain contract still has other consumers, its existing YAML remains the sole owner and its CUE projection is checked against the same source snapshot. Original owner evaluators retain their cross-reference, graph, capability, and other semantic checks. Passing CUE alone does not replace this complete validation. No validator executes natural-language answers as code.

## What belongs in a Profile

A selected Profile may hold stable, repository-specific choices such as scope, logical directories, language, terminology, sources, priority predicates, role bindings, review predicates, and enabled Kernel extensions. It may also hold stable references to Read Sets, Tool capabilities, host capabilities, or corpus artifacts without taking ownership of their contents, implementation, or current state.

The `Priority Rubric` always supplies the repository's P0/P1 grant predicates. Its numeric `priority_quota` is optional: `mode = "none"` activates no corpus-share ceiling, while `mode = "configured"` supplies a user-confirmed P0/P1 pair and rationale under K00/07. Quota values are numeric fractions, not formatted percentages. Absence of a quota never weakens the grant predicates.

A Profile does not hold Kernel defaults, common slot schemas, Card steps, Read Set membership, Tool implementation details, task-time choices, Queue or Coverage data, receipts, recovery data, or adoption history. Current selection and execution evidence belong under `.cambium/`; that namespace is not a second store for all Profile answers or interview history.

## Candidate creation

The user discusses and confirms decisions; the assisting agent creates and edits the candidate through Tools. No manual template copying or TOML transcription is required. Start from a Cambium source checkout with the [isolated Profile toolchain](../Tools/README.md#profile-toolchain), then let the agent preview and apply creation after the Profile identity is confirmed:

```sh
python3 Tools/scaffold_profile.py . --profile-id my-profile
python3 Tools/scaffold_profile.py . --profile-id my-profile --apply
```

The new `profile.toml` starts with the confirmed identity and empty slots. Then use [`interview.yaml`](interview.yaml) and [`answer-patterns.md`](answer-patterns.md) to discuss the repository's actual needs. Interview mappings point to semantic answer paths, not file names, Markdown headings, or table cells. Inactive choices such as `None`, `not-applicable`, or `kernel-defaults` must not be inferred from unanswered questions. Existing legal defaults remain legal where the completed contract permits them; omission alone does not prove confirmation.

The sole candidate template lives in [`_template/`](_template/). [`template-files.yaml`](template-files.yaml) declares the exact copy whitelist; the template's README is orientation and is deliberately not copied. Unreferenced supporting files do not supply answers or become active policy. Answer depth comes from the interview, not another template tier.

## Agent read, edit, and review

Read the candidate before proposing a change. The result includes the package's `snapshot_sha256`:

```sh
python3 Tools/profile_candidate.py . --profile-id my-profile --mode read --json
```

The agent prepares an explicit JSON edit file from the discussed answers, previews it against that hash, then applies the same edit only after reviewing the result:

```sh
python3 Tools/profile_candidate.py . --profile-id my-profile --mode edit \
  --edits <edits.json> --expected-snapshot-sha256 <snapshot_sha256> --json
python3 Tools/profile_candidate.py . --profile-id my-profile --mode edit \
  --edits <edits.json> --expected-snapshot-sha256 <snapshot_sha256> --apply --json
python3 Tools/profile_candidate.py . --profile-id my-profile --mode render
```

The edit file is an array of `set`, `append`, or `remove` operations. For example, this *illustrative* edit supplies one answer—it is not a recommended answer or a complete slot:

```json
[
  {
    "op": "set",
    "path": ["slots", "profile-scope"],
    "value": {
      "goal": {
        "statement": "Explain how this example system works.",
        "readers": ["Repository maintainers"]
      }
    }
  }
]
```

`set` replaces the addressed value: setting an entire slot replaces that slot, so use a narrower path once other answers exist. Parent objects must already exist. Arrays are addressed by stable record identity, not row number; for a candidate with the named layer, a selector could be:

```sh
python3 Tools/profile_candidate.py . --profile-id my-profile --mode read \
  --selector '["slots","profile-scope","logical_architecture",{"layer_id":"L-FOUNDATION"},"responsibility"]' --json
```

The editor accepts only answer paths under `slots` or `execution_default_overrides`, checks the draft against the bound contracts, and refuses stale snapshots. It does not change the identity or version, edit referenced body files, infer missing answers, or perform adoption. Natural-language values remain intact through the TOML codec. A successful edit may still leave the draft incomplete. `adoption_performed: false` describes this operation; it does not assert whether a Profile was previously selected. If the result is `uncertain`, inspect and reread the candidate before retrying.

Rendered output is a non-authoritative review view, not another Profile file. Read, render, and onboarding status never change current selection. A snapshot hash is a concurrency precondition, not evidence of user approval.

## Mechanical validation and adoption

Ask for the next unresolved decision and validate a filled candidate with:

```sh
python3 Tools/profile_onboarding_status.py . --profile-id my-profile --json
python3 Tools/check_profile.py profiles/my-profile
```

Validation proves only mechanical matters such as shape, allowed values, identity, reference closure, and machine consistency. It does not prove that the answers are appropriate, that the user confirmed them, or that the Profile has been adopted.

A directory, valid manifest, template, example, or rendered view never becomes active merely by existing. Confirmation of the answers and authorization to adopt are distinct from validation. A Profile is selected only by the authorized Standards adoption operation; the selected identity and its history are adopter runtime state under `.cambium/`. Follow the [R09 adoption workflow](../README.md#3-approve-the-profile-through-r09), including its real corpus evidence requirements. Candidate creation is not a shortcut around them.

## Revising an adopted Profile

The template, interview, answer patterns, and authoring commands belong to the Cambium source distribution, not the carried adopter runtime; see [`distribution-boundary.yaml`](../distribution-boundary.yaml). For a later authorized revision, use the authoring guidance from a source checkout matching the intended Standards version to discuss the changed answers. Do not reinstall the authoring kit into the adopter or interpret this as a fresh onboarding transition.

An existing task keeps its runtime/resume precedence. Prepare the candidate within the authorized R09 revision and use the existing [Standards adoption transaction](../Tools/README.md#profile-candidate-workflow) to bind the accepted after-image. Neither the interview nor candidate editing replaces that transaction or writes a second selection record.

For the semantics of any slot, follow its `kernel_owner` entry in the Kernel-owned interface registry.
