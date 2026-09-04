# Audit Dimension Registry

Kernel owner: K12 Quality Assurance. Common slot identity and table contract are registered in the Kernel Profile interface.

## Extension Dimensions

- Registration: None

This Profile registers no additional audit dimension.

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|

## Judgment Items

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `agent-atlas-foundation-depth` | `content_and_depth` | `Single Note Review` | One page of a registered foundation class satisfies the Profile foundation-depth predicate. | `emits` | `profiles/examples/agent-atlas/scope-and-architecture.md#Foundation Depth Requirements` |
| `agent-atlas-residual-disposition` | `coverage_and_integration` | `Batch Review` | Every candidate reported by the registered residual scan has an accepted disposition. | `emits` | `profiles/examples/agent-atlas/registries/audit-dimensions.md#Residual Disposition` |

## Residual Disposition

A reported candidate identifies content that may belong under `Interview Preparation`; accept it only after recording either its target artifact or a bounded reason that it remains canonical knowledge content.
