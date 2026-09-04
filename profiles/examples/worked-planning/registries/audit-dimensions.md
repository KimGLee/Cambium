# Audit Dimension Registry

Interface: [Kernel-owned Profile interface](../../../../kernel/K00%20Standards%20Control/profile-interface.yaml) — Audit Dimension Registry slot

## Extension Dimensions

- Registration: None

This profile registers no extension dimension because its four judgment items use the existing base receipt dimensions.

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `worked-planning-foundation-depth` | `content_and_depth` | `Module Review` | The foundation pages one procedure depends on satisfy the registered depth predicate. | `emits` | `profiles/examples/worked-planning/scope-and-architecture.md#Foundation Depth Requirements` |
| `worked-planning-case-residual-disposition` | `coverage_and_integration` | `Batch Review` | Every service-case-structure candidate the registered scan reports outside the case layer has an accepted disposition. | `emits` | `profiles/examples/worked-planning/registries/audit-dimensions.md#Case Residual Disposition` |
| `worked-planning-capability-evidence-resolves` | `source_and_currentness` | `Module Review` | Every Capability Matrix row above the lowest scale rank names evidence paths that resolve in the reviewed snapshot. | `consumes` | `profiles/examples/worked-planning/registries/audit-dimensions.md#Capability Evidence Resolves` |
| `worked-planning-source-revision-drift` | `source_and_currentness` | `Module Review` | Pages quoting a figure from a superseded document revision are raised as review candidates. | `triggers` | `profiles/examples/worked-planning/registries/audit-dimensions.md#Source Revision Drift` |

### Capability Evidence Resolves

This item is satisfied by the `corpus-plan-structure` gate receipt for the same snapshot, which already proves that every Capability Matrix evidence path resolves and that a capability above the scale's lowest rank names at least one. Review records the reused receipt ID rather than re-deriving the verdict, and does not change that receipt's dimension.

### Source Revision Drift

When a newer revision of a held document reaches the workshop, every page quoting a figure from the superseded revision becomes a review candidate. This item raises candidates only: it produces no receipt and cannot fail a gate by itself. The disposition of each candidate belongs to the review that consumes it.

## Residual Disposition

### Case Residual Disposition

The registered scan reports canonical pages that still carry service-case structure: a `type: service-case` declaration, a `Service Case Log` heading, or at least two distinct intake/parts/bench-time headings that belong only on a case page. Each candidate is resolved on the page itself — the case material moves to the case layer, or the page states why that structure is canonical there.

The scan is candidate discovery only. A zero-candidate result proves the registered predicate for the scanned snapshot and nothing about case quality.
