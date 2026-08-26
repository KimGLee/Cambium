# Audit Dimension Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Audit Dimension Registry slot

## Extension Dimensions

- Registration: None

This profile files every judgment item under a base kernel receipt dimension. It registers no extension dimension because it has no artifact class whose fitness is judged independently of the seven base dimensions.

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

The required starter row registers Foundation Depth; copy it for other profile-owned audit predicates.

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `minimal-notes-foundation-depth` | `content_and_depth` | `Single Note Review` | One device or service page satisfies the registered foundation-depth predicate. | `emits` | `profiles/examples/minimal-notes/scope-and-architecture.md#Foundation Depth Requirements` |
| `minimal-notes-scratch-residual-disposition` | `coverage_and_integration` | `Batch Review` | Every scratch-structure candidate the registered scan reports outside `Notes/Daily Log` has an accepted disposition. | `emits` | `profiles/examples/minimal-notes/registries/audit-dimensions.md#Scratch Residual Disposition` |

## Scratch Residual Disposition

The registered scan reports canonical notes that still carry dated-scratch structure: a `type: daily-log` declaration, a `Daily Log Entry` heading, or at least two distinct sorting headings that belong only in a dated entry. Each candidate is resolved one of two ways, and the resolution is recorded on the candidate page: the scratch material is moved into the dated entry that owns it, or the page states why that structure is the canonical form for this note.

The scan is candidate discovery only. A zero-candidate result proves the registered predicate for the scanned snapshot; it proves nothing about note quality or coverage.
