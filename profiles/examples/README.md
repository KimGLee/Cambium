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

## Included Examples

- [Agent Systems Atlas](agent-atlas/README.md) — a Chinese-first engineering knowledge corpus that uses kernel route R05 for an Interview expression layer and binds an Atlas-specific residual scan to the generic tool implementation.
