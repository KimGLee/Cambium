# Agent Systems Atlas Example Profile

## What This Example Is

This directory is a non-normative, filled example of the Cambium profile interface for a real Chinese-first engineering knowledge corpus. It is not a template, default configuration, or adoption certificate. Because it lives under `profiles/examples/`, its manifest is intentionally not selectable in place.

The normative interface is [profiles/README.md](../../README.md), and cross-domain rules remain in the kernel. A real adopter copies [profiles/_template/](../../_template/profile.md) to `profiles/<profile-id>/`, fills and validates that copy, and selects it through governance.

The example does not contain or synchronize the live Agent Systems Atlas vault. Agent Systems Atlas has since completed a separate formal adoption of Cambium `3.0.0` using a materialized `profiles/agent-atlas/` profile. That instance state, migration evidence, and private corpus are not distributed here, so this example remains a reference rather than an adoption certificate or proof of corpus-wide acceptance.

## Directory Structure

The directory contains 13 published files:

| Role | Count | Meaning |
|---|---:|---|
| Filled profile skeleton | 11 | [profile.md](profile.md) plus the ten bound slot files corresponding to `_template/` |
| Example orientation | 1 | This README; it is not loaded as profile policy |
| Registered-scan parameters | 1 | [scan-configs/interview-residuals.yaml](scan-configs/interview-residuals.yaml), consumed by one scan registration |

[profile.md](profile.md) is the authoritative file map. Its Execution Default Overrides table is empty, so this example keeps every kernel execution default.

The scan configuration is not another slot or standard. This example has no separate Interview standards directory, supplemental Profile Read Set, profile-owned executable, or plugin.

## Atlas-specific Bindings

K11 owns the universal expression-layer floor. This profile supplies only the Atlas-specific answers: what an Interview artifact is, how it binds to canonical knowledge, how bilingual answers and readiness work, and what becomes a residual-content candidate.

| Atlas concern | Existing profile owner |
|---|---|
| Corpus goal, exclusions, layers, placement, and `Interview Preparation/` organization | [scope-and-architecture.md](scope-and-architecture.md) |
| Priority grants | [priority-rubric.md](priority-rubric.md) |
| Atlas fields, values, and `interview_status` | [vocabulary-extensions.yaml](vocabulary-extensions.yaml) |
| Chinese-first writing and bilingual Interview answers | [language-contract.md](language-contract.md) |
| Interview Card, Roadmap, and Cheat Sheet contracts | [expression-layer.md](expression-layer.md) |
| Source authorities and staleness triggers | [source-policy.md](source-policy.md) |
| Actors and acceptance judgments | [registries/roles.md](registries/roles.md) and [registries/audit-dimensions.md](registries/audit-dimensions.md) |
| L-tier triggers, specialized invariant, and readiness gate | [registries/routing-and-gates.md](registries/routing-and-gates.md) |
| Residual scan ID, scope, candidate boundary, and judgment binding | [registries/registered-scans.md](registries/registered-scans.md) |
| Literal residual matchers and excluded roots | [scan-configs/interview-residuals.yaml](scan-configs/interview-residuals.yaml) |

Interview work uses kernel route R05 directly. `Supplemental Routes` is `None`, and no supplemental Read Set is needed. The profile owns the residual scan identity, scope, predicate, judgment binding, and configuration; the generic executable belongs to [Tools/check_residual_content.py](../../../Tools/check_residual_content.py).

## How To Read, Validate, And Reuse It

1. Read [profile.md](profile.md) for identity and bindings.
2. Read the corpus-wide slot files, then [expression-layer.md](expression-layer.md) and the registries for the Atlas-specific Interview contract.
3. Inspect the scan configuration last; it contains machine parameters, not policy.

Validate the filled profile structure from the Cambium repository root:

```text
python3 Tools/check_profile.py profiles/examples/agent-atlas
```

Run the registered residual scan against the live vault root, not this example directory:

```text
python3 Tools/check_residual_content.py "/path/to/Agent Systems Atlas" \
  --scan-id agent-atlas-interview-residuals \
  --config profiles/examples/agent-atlas/scan-configs/interview-residuals.yaml \
  --time-limit 55
```

Exit 2 means the scan produced candidates for the registered judgment item. It is not a defect count, deletion list, migration authorization, or automatic gate failure.

Reuse the answer shape—bounded applicability, stable IDs, testable predicates, single-owner pointers, and deterministic candidate boundaries. Do not reuse Atlas identity, paths, language choices, priority criteria, vocabulary, sources, roles, Interview structure, gate IDs, exclusions, or pre-adoption states as another profile's defaults.
