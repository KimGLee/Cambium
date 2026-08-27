# Worked Planning Example Profile

## What This Example Is

This directory is a non-normative, filled example of the Cambium profile interface for a community bicycle workshop's wheel-service corpus. Its subject is the one thing no other example in this repository could show: a **configured Corpus Planning slot with all three planning artifacts actually filled in and passing `check_corpus_plan.py`**.

It is not a template, a default configuration, or a claim that a corpus this small needs a plan. Because it lives under `profiles/examples/`, its manifest is intentionally not selectable in place.

The common interface is owned by [K00/19](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md); the three artifact contracts are owned by [K02/05](../../../kernel/K02%20Knowledge%20Work%20Construction/05%20Global%20Map%20Contract.md), [K02/06](../../../kernel/K02%20Knowledge%20Work%20Construction/06%20Capability%20Matrix%20Contract.md), and [K02/07](../../../kernel/K02%20Knowledge%20Work%20Construction/07%20Gap%20Register%20Contract.md).

## Why The Corpus Is Inside The Package

A Global Map entry must name a Markdown file that really exists, and a Profile Scope layer must name a directory that really exists — otherwise `check_corpus_plan.py` cannot resolve them. So this package carries a six-page micro-corpus under [corpus/](corpus/), and its Profile Scope layer directories point at it.

**A real adopter does not do this.** Layer directories are vault-root-relative and live outside `profiles/`; the corpus is the thing being governed, not part of the profile that governs it. The nesting here exists only so that every path in the three artifacts resolves inside this repository and the checker's output is real rather than illustrative.

## Directory Structure

| Role | Count | Meaning |
|---|---:|---|
| Filled profile skeleton | 15 | [profile.md](profile.md) plus the fourteen bound slot files corresponding to `_template/` |
| Example orientation | 1 | This README; it is not loaded as profile policy |
| Registered-scan parameters | 1 | [scan-configs/residual-scan.yaml](scan-configs/residual-scan.yaml), consumed by the one scan registration |
| Planning artifacts | 3 | [planning/](planning/), bound by [corpus-planning.yaml](corpus-planning.yaml) and owned by K02/05–07 |
| Micro-corpus | 6 | [corpus/](corpus/), the governed pages the artifacts point at |

## Reading Order

1. [corpus-planning.yaml](corpus-planning.yaml) — the slot: applicability, the three bindings, the ordered capability scale, and the pass authority.
2. [planning/global_map.yaml](planning/global_map.yaml) — six entries, one per page, plus eight typed dependency edges.
3. [planning/capability_matrix.yaml](planning/capability_matrix.yaml) — three capabilities at three different scale positions.
4. [planning/gap_register.yaml](planning/gap_register.yaml) — four gaps in four different statuses.
5. [scope-and-architecture.md](scope-and-architecture.md) — the Layer IDs everything above references.

## What The Artifacts Demonstrate

- **All eight `relation_type` values**, one per edge in the Global Map, each on a pair of entries where that relation is the honest one.
- **Three capability positions**: above the lowest rank and below target (needs both evidence and a Gap ID); at target (needs neither); still at rank `0` (the only position where `evidence_paths` may legally be `[]`).
- **The empty-list branch**, written as an explicit `[]` exactly where K02/06 and K02/07 permit it — `evidence_paths` and `gap_ids` in the Matrix, `evidence_paths` in the Register — and never for `map_entry_ids`, `canonical_markdown_paths`, or `capability_ids`, which those modules require to carry at least one value.
- **Bidirectional Matrix–Gap links**, including a `rejected` gap and a `deferred` gap that a capability still names.
- **One legal Execution Default Overrides row** ([profile.md](profile.md)), using `priority_quota.P0` — the item this distribution's tools actually resolve from the manifest.
- **Judgment items with all three evidence roles**: `emits`, `consumes` (satisfied by the `corpus-plan-structure` receipt), and `triggers` (raises candidates, produces no receipt).

## What It Does Not Demonstrate

- **Gap statuses `promoted` and `resolved` are absent.** Both require a real Coverage object and initialized runtime state under `.cambium/`; this repository deliberately carries neither, and `check_corpus_plan.py` refuses to reconcile a promotion without them. Four of the six statuses appear here; the promotion handoff itself has no worked example anywhere.
- **No semantic acceptance receipt.** `check_corpus_plan.py` reports `semantic_acceptance=not-recorded` for this package. Structure is not acceptance: recording acceptance requires `record_corpus_acceptance.py`, the bound authority role, and runtime state.
- **No expression layer, readiness axis, supplemental route, profile Read Set, or extension gate.** See [agent-atlas](../agent-atlas/README.md) for the first two; the last two still have no example.
- **Not a minimal profile.** For the shortest legal path, read [minimal-notes](../minimal-notes/README.md) first.

## Materialization Warning

The verifier command in [registries/registered-scans.md](registries/registered-scans.md), the predicate-owner cells in [registries/audit-dimensions.md](registries/audit-dimensions.md), the three artifact bindings, and every path inside `planning/` contain this example's own repository path. If you materialize the answer shape, rewrite every `profiles/examples/worked-planning/...` string to the intended Profile or corpus path. `check_profile.py` fails closed on the Profile-owned config and predicate-owner edges through `profile-load`; `check_corpus_plan.py` remains the separate owner of the externally bound planning artifacts and their corpus paths. Neither checker guesses a replacement.

## Validation Provenance

The public Cambium distribution is intentionally uninstantiated: it carries no `.cambium/governance/standards_state.yaml`, so there is no adopter version string for an example to declare. The machine-checkable stand-in is the validating tool version below. Re-run every command in this table — and update the versions — after any Standards revision, interface change, or tool bump; `Tools/tests/test_profile_examples.py` enforces exactly this table.

| Validator | Tool version | Command | Expected result |
|---|---|---|---|
| `check_profile` | `2.2.0` | `python3 Tools/check_profile.py profiles/examples/worked-planning` | exit 0 |
| `check_corpus_plan` | `1.7.0` | `python3 Tools/check_corpus_plan.py . --profile profiles/examples/worked-planning/profile.md` | exit 0 |
| `check_residual_content` | `1.2.0` | `python3 Tools/check_residual_content.py . --scan-id worked-planning-case-residuals --config profiles/examples/worked-planning/scan-configs/residual-scan.yaml --time-limit 55` | exit 0 |

The residual scan is runnable here only because this package's micro-corpus lives inside the repository: the accepted root `corpus/Service Cases` exists, so the scan's non-triviality control finds its witness there.

## Reuse Boundary

Reuse the artifact *shape* — stable IDs, explicit typed edges, one responsibility per entry, evidence that resolves, and a gap whose status carries its own reason. Do not reuse this workshop's scale wording, capability set, priority grants, or its judgment that four gaps are the whole picture.
