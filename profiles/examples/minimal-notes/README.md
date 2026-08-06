# Minimal Notes Example Profile

## What This Example Is

This directory is a non-normative, filled example of the Cambium profile interface for the smallest corpus the interface still governs: one person's home-network notes, kept in a plain Markdown tree. It exists to show the **shortest legal path to a loadable profile**. It is not a template, a default configuration, or a recommendation to configure this little.

The normative interface is [profiles/README.md](../../README.md), and cross-domain rules remain in the kernel. A real adopter copies [profiles/\_template/](../../_template/profile.md) to `profiles/<profile-id>/`, fills and validates that copy, and selects it through governance. Because this directory lives under `profiles/examples/`, its manifest is intentionally not selectable in place.

Read this example first, then [Agent Systems Atlas](../agent-atlas/README.md). Atlas answers the same eleven slots for a large bilingual corpus with an expression layer; the difference between the two packages is domain need, not compliance.

## Directory Structure

The directory contains 14 published files:

| Role | Count | Meaning |
|---|---:|---|
| Filled profile skeleton | 12 | [profile.md](profile.md) plus the eleven bound slot files corresponding to `_template/` |
| Example orientation | 1 | This README; it is not loaded as profile policy |
| Registered-scan parameters | 1 | [scan-configs/residual-scan.yaml](scan-configs/residual-scan.yaml), consumed by the one scan registration |

The vault this profile describes — `Notes/` and `Notes/Daily Log/` — is the adopter's own tree and is not part of this repository, exactly as with the Atlas example.

## What It Demonstrates

Every optional and conditional switch in `profiles/_template/` is in its **inactive** form here. That is the point of the package: the Atlas example configures fourteen of the fifteen switches, so before this package existed the repository showed almost no worked "off" state.

| Answer shape | Where |
|---|---|
| `Conditional` answered as `Not applicable — <reason>` | [scope-and-architecture.md](scope-and-architecture.md) (three switches), [registries/roles.md](registries/roles.md) |
| `Excluded Scope: None — no exclusions` | [scope-and-architecture.md](scope-and-architecture.md#excluded-scope) |
| Unused layer roles as `None` plus a fallback Layer ID, and an unused expression predicate as `always false` | [scope-and-architecture.md](scope-and-architecture.md#placement-layer-registrations) |
| Corpus Planning in the `not-applicable` branch | [corpus-planning.yaml](corpus-planning.yaml) |
| A Priority Rubric that grants nothing | [priority-rubric.md](priority-rubric.md) |
| Vocabulary extensions with an empty `frontmatter_extensions.fields` and the readiness-axis mapping deleted | [vocabulary-extensions.yaml](vocabulary-extensions.yaml) |
| A monolingual Language Contract | [language-contract.md](language-contract.md) |
| Zero registered expression artifacts | [expression-layer.md](expression-layer.md) |
| Source Policy with both optional sections `None` | [source-policy.md](source-policy.md) |
| `knowledge-host UI: None — headless` and metric traceability not applicable | [registries/roles.md](registries/roles.md) |
| An Audit Dimension Registry with no extension dimension | [registries/audit-dimensions.md](registries/audit-dimensions.md) |
| A Routing And Gate Registry whose four subsections are all `None` | [registries/routing-and-gates.md](registries/routing-and-gates.md) |

Two things are still filled, because the interface makes them Required rather than optional: the Audit Dimension Registry carries the Foundation Depth judgment item plus the one acceptance item its scan needs, and the Registered Scan Registry binds a real residual-content verifier. A profile cannot opt out of those two.

## What It Does Not Demonstrate

This package is deliberately silent on everything an "off" state cannot show. Do not read its absence of these as guidance:

- **No filled Global Map, Capability Matrix, or Gap Register.** Corpus Planning is `not-applicable` here. The worked instances live in [worked-planning](../worked-planning/README.md).
- **No expression artifact, readiness axis, readiness gate, supplemental route, profile Read Set, extension dimension, or L-tier trigger.** Atlas shows the configured forms of the first five; a profile Read Set has no example anywhere yet.
- **No Execution Default Overrides row.** This profile keeps every kernel execution default, so its table is empty. A worked override row is in [worked-planning](../worked-planning/profile.md).
- **No non-generic scan verifier and no additional candidate scan.** This package registers exactly one scan and uses the generic `Tools/check_residual_content.py` matcher.
- **No judgment item with evidence role `consumes` or `triggers`.** Both items here `emit`.
- **Nothing about answer quality.** `check_profile.py` checks structure; that these answers are the right answers for a home-network vault is a human call.

## Materialization Warning

The verifier command in [registries/registered-scans.md](registries/registered-scans.md) and the predicate-owner cells in [registries/audit-dimensions.md](registries/audit-dimensions.md) contain this example's own repository path. If you copy this package into your own repository, rewrite every `profiles/examples/minimal-notes/...` string to your profile's path first; nothing in `check_profile.py` will notice if you do not, and the batch-close scan would then run this example's configuration instead of yours.

## Validation Provenance

The public Cambium distribution is intentionally uninstantiated: `kernel/K00 Standards Control/03 Standards Governance.md` still carries `{{ standards_version }}`, so there is no released version string for an example to declare. The machine-checkable stand-in is the validating tool version below. Re-run every command in this table — and update the versions — after any Standards revision, interface change, or tool bump; `Tools/tests/test_profile_examples.py` enforces exactly this table.

| Validator | Tool version | Command | Expected result |
|---|---|---|---|
| `check_profile` | `1.6.0` | `python3 Tools/check_profile.py profiles/examples/minimal-notes` | exit 0 |
| `check_corpus_plan` | `1.5.0` | `python3 Tools/check_corpus_plan.py . --profile profiles/examples/minimal-notes/profile.md` | exit 0 |

The registered residual scan is not in that table: it runs against a live vault root, which this repository does not contain.

## Reuse Boundary

Reuse the answer *shape* — an inactive switch is a declaration plus a reason, never a blank. Do not reuse this profile's identity, paths, scale of ambition, or the judgment that a corpus plan is unnecessary; that judgment is owned by [K02/03](../../../kernel/K02%20Knowledge%20Work%20Construction/03%20Corpus%20Planning%20Applicability%20and%20Lifecycle.md), and a corpus that grows into multi-batch construction must configure the slot.
