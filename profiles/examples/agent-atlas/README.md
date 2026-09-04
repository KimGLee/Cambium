# Agent Systems Atlas Example Profile

## What This Example Is

This directory is a Cambium-owned, non-normative example of a filled Profile for a Chinese-first engineering knowledge corpus. It is not a template, default configuration, live mirror, or adoption certificate. Because it lives under `profiles/examples/`, its manifest is intentionally not selectable in place.

The common interface is owned by the [Kernel Profile registry](../../../kernel/K00%20Standards%20Control/profile-interface.yaml), and cross-domain rules remain in the Kernel. A real adopter copies [profiles/_template/](../../_template/profile.md) to `profiles/<profile-id>/`, fills and validates that copy, and selects it through governance.

The example does not contain the adopter corpus, runtime state, or gate evidence. It remains a reference profile rather than an adoption certificate or proof of corpus-wide acceptance.

## Directory Structure

The directory contains 17 published files: 16 machine-active Profile files and this orientation README.

| Role | Count | Meaning |
|---|---:|---|
| Profile manifest and bound slots | 15 | [profile.md](profile.md) plus the fourteen slot files corresponding to `_template/` |
| Example orientation | 1 | This README; it is not loaded as profile policy |
| Registered-scan parameters | 1 | [scan-configs/residual-scan.yaml](scan-configs/residual-scan.yaml), consumed by one scan registration |

[profile.md](profile.md) is the authoritative file map. Its Execution Default Overrides table is empty, so this example keeps every kernel execution default.

The scan configuration is not another slot or standard. This example has no separate Interview standards directory, supplemental Profile Read Set, profile-owned executable, or plugin.

## Content Provenance

The original package was seeded from the Agent Systems Atlas Profile at commit `15df10eac89cafd381b145c48659c4a525f93f6d`. On 2026-09-04, its 16 machine-active files were reconciled with the current Atlas Profile values and the current Cambium Profile contract. These statements record content provenance only: they do not assert that this example is selected, that the live Atlas repository has adopted the current Cambium baseline, or that either repository's runtime state is represented here.

The current example makes only these package-location adaptations:

- the Profile root changes from `profiles/agent-atlas/` to `profiles/examples/agent-atlas/`;
- Profile-owned paths are rewritten to that example root; and
- relative Kernel links gain the additional `examples/` directory level.

Apart from those location adaptations, the example preserves the current Atlas Profile values and file shapes. Cambium owns this public example and may evolve it to demonstrate the current public Profile contract; the live Atlas Profile is not a continuing synchronization authority. Atlas and every other adopter must explicitly adopt and materialize applicable Cambium changes through its own governance process, and Cambium does not write or manage an adopter's runtime state.

## Atlas-specific Bindings

K11 owns the universal expression-layer floor. This profile supplies only the Atlas-specific answers: which Interview artifacts exist, where they live, how they bind to canonical knowledge, and what becomes a residual-content candidate. It registers no separate Interview-readiness axis.

| Atlas concern | Existing profile owner |
|---|---|
| Corpus goal, exclusions, layers, content placement, and `Interview Preparation/` organization | [scope-and-architecture.md](scope-and-architecture.md) |
| Global Map, Capability Matrix, Gap Register, capability scale, and corpus-planning pass authority | [corpus-planning.yaml](corpus-planning.yaml) |
| Priority grants | [priority-rubric.md](priority-rubric.md) |
| Atlas fields and values, including `interview_guide` and `interview-topic-guide` | [vocabulary-extensions.yaml](vocabulary-extensions.yaml) |
| Chinese-first writing and preserved external identities | [language-contract.md](language-contract.md) |
| Interview Topic Guide, Roadmap, and Cheat Sheet registrations | [expression-layer.md](expression-layer.md) |
| Source authorities and staleness triggers | [source-policy.md](source-policy.md) |
| Actors and instance judgment items | [registries/roles.md](registries/roles.md) and [registries/audit-dimensions.md](registries/audit-dimensions.md) |
| Optional routing and Gate extensions, currently inactive | [registries/routing-and-gates.md](registries/routing-and-gates.md) |
| Residual scan ID, scope, candidate boundary, and judgment binding | [registries/registered-scans.md](registries/registered-scans.md) |
| Literal residual matchers and excluded roots | [scan-configs/residual-scan.yaml](scan-configs/residual-scan.yaml) |

Interview work uses kernel route R05 directly. `Supplemental Routes` is `None`, and no supplemental Read Set is needed. The profile owns the residual scan identity, scope, predicate, judgment binding, and configuration; the generic executable belongs to [Tools/check_residual_content.py](../../../Tools/check_residual_content.py).

## How To Read, Validate, And Reuse It

1. Read [profile.md](profile.md) for identity and bindings.
2. Read [scope-and-architecture.md](scope-and-architecture.md) and [corpus-planning.yaml](corpus-planning.yaml), then the remaining corpus-wide slot files, [expression-layer.md](expression-layer.md), and the registries for the Atlas-specific Interview contract.
3. Inspect the scan configuration last; it contains machine parameters, not policy.

The registry command and predicate-owner cells use this example package's own paths. A real Profile materializes those cells with its own path before validation. `profile-load` rejects a stale example or foreign-Profile target; it reports the value but never rewrites it on the adopter's behalf.

Validate the filled profile structure from the Cambium repository root:

```text
python3 Tools/check_profile.py profiles/examples/agent-atlas
```

That command validates the self-contained Profile package, not the three bound planning artifacts or the private corpus. `check_corpus_plan.py` is run only after this profile has been materialized as a selectable direct-child profile inside the adopting repository and the three bound restricted-YAML artifacts under `Corpus Planning/` exist there. The public example intentionally does not fabricate those files or a passing corpus-planning receipt.

Run the registered residual scan against the live vault root, not this example directory:

```text
python3 Tools/check_residual_content.py "/path/to/Agent Systems Atlas" \
  --scan-id agent-atlas-residual-content \
  --config profiles/examples/agent-atlas/scan-configs/residual-scan.yaml \
  --time-limit 55
```

Exit 2 means the scan produced candidates for the registered judgment item. It is not a defect count, deletion list, migration authorization, or automatic gate failure.

## Validation Provenance

The public Cambium distribution is intentionally uninstantiated: it carries no `.cambium/governance/standards_state.yaml`, so there is no adopter version string for an example to declare. The machine-checkable stand-in is the validating tool version below. Re-run every command in this table — and update the versions — after any Standards revision, interface change, or tool bump; `Tools/tests/test_profile_examples.py` enforces exactly this table.

| Validator | Tool version | Command | Expected result |
|---|---|---|---|
| `check_profile` | `2.2.0` | `python3 Tools/check_profile.py profiles/examples/agent-atlas` | exit 0 |

`check_corpus_plan.py` is deliberately absent from that table: this example's Corpus Planning slot is `configured` and binds three artifacts that a real adopter materializes, and the public example does not fabricate them. [Worked Planning](../worked-planning/README.md) is the example that carries filled planning artifacts.

Reuse the answer shape—bounded applicability, stable IDs, testable predicates, single-owner pointers, and deterministic candidate boundaries. Do not reuse Atlas identity, paths, language choices, priority criteria, vocabulary, sources, roles, Interview structure, gate IDs, exclusions, or pre-adoption states as another profile's defaults.
