# Profile Examples

## Purpose

This directory contains non-normative, filled reference cases. An example shows what concrete, testable answers to the profile interface can look like in one domain. It does not define the interface, supply kernel defaults, or constrain another profile.

The distinction is deliberate:

- `profiles/README.md` defines the slots and their constraints.
- `profiles/_template/` asks an adopter to provide its own answers.
- `profiles/examples/` shows completed domain-specific answers for reference.

## Selection Boundary

Examples are not templates or adoption starting points. The active-selection contract accepts exactly `profiles/<profile-id>/profile.md`; manifests nested under `profiles/examples/` are intentionally not selectable in place.

Start from `_template`, create `profiles/<profile-id>/`, fill and validate that copy, and then select it through governance. Consult examples for answer shape and specificity without inheriting their domain choices.

## Example Package Shape

Every example contains the filled template skeleton and may also contain:

- an example-specific README that explains its domain and reading order;
- machine parameters or other support data explicitly consumed by an existing slot registration.

Additional support files do not create slots or extend the profile interface. Policy remains in the bound slot owners, and persistent executable code shipped by Cambium remains under `Tools/`. An example must identify auxiliary files and explain why they exist.

Every example README carries a `## Validation Provenance` table: for each validator the example claims to pass, the tool version it was last validated against, the exact command, and the expected result. The public distribution is intentionally uninstantiated and therefore has no `standards_version` for an example to name, so the tool version is the machine-checkable stand-in. `Tools/tests/test_profile_examples.py` re-runs every command in every such table and fails when a declared version no longer matches the tool.

## Included Examples

- [Minimal Notes](minimal-notes/README.md) — the shortest legal path to a loadable profile: one layer, monolingual, no expression artifact, `corpus_planning: not-applicable`, and every optional switch in its inactive form. Read this one first.
- [Agent Systems Atlas](agent-atlas/README.md) — a Chinese-first engineering knowledge corpus that uses kernel route R05 for an Interview expression layer and binds an Atlas-specific residual scan to the generic tool implementation.
- [Worked Planning](worked-planning/README.md) — a configured Corpus Planning slot with a filled Global Map, Capability Matrix, and Gap Register that pass `check_corpus_plan.py`, over a six-page micro-corpus carried inside the package.

## Branch Coverage

The three examples together are not a complete tour of the interface, and this section names what is still missing so that an absent form is not read as a forbidden one.

Between them the examples now show both sides of every optional and conditional switch in `profiles/_template/` that existed when they were written: Atlas configures seventeen of the eighteen, Minimal Notes leaves all eighteen inactive, and each package states the reason for its own choice. The optional K08/09 `boundary_projection` key added later is left in its inactive kernel-default form by every example (see the table below).

Documented forms that still have **no** worked example anywhere in this repository:

| Missing form | Why it is missing |
|---|---|
| A supplemental route with its profile Read Set (`type: profile-read-set`) | No example needs a route the kernel does not already provide; the file shape is documented only in prose in `profiles/README.md`. |
| Gap Register statuses `promoted` and `resolved` | Both require a real Coverage object and initialized `.cambium/` runtime state, which this repository deliberately does not carry. |
| A non-generic deterministic residual verifier, and additional optional candidate scans | Every example is served by the generic `Tools/check_residual_content.py` matcher with one registered scan. |
| A profile-owned extension audit dimension beyond the one Atlas registers | Not needed by the other two domains. |
| A `boundary_projection` display-label override, or a profile-closed `boundary` concern vocabulary | The K08/09 kernel display labels and the open (shape-checked only) concern-slug state are the intended defaults during a corpus's boundary migration; closing the vocabulary is a later governance decision no example has reached. |

An adopter who needs one of these writes it from the interface text and the kernel owner, not from an example.
