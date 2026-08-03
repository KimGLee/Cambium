# Audit Dimension Registry

Interface: [Audit Dimension Registry slot](../../../README.md#audit-dimension-registry-slot)

## Extension Dimensions

- Registration: Configured

| Dimension ID | Target list(s): `review`, `receipt`, or `review + receipt` | Meaning |
|---|---|---|
| `interview` | `review + receipt` | Fitness of Agent Systems Atlas Interview Cards for their registered spoken-answer and evaluation use, independent of authoring, evidence, and learning status. |

## Judgment Items

| Stable Judgment Item ID | Base or registered receipt Dimension ID | Exact kernel audit-layer name | Bounded audit object one run proves | Evidence role: `emits`, `consumes`, or `triggers` | Predicate owner (repo-relative path; optional `#heading`) |
|---|---|---|---|---|---|
| `agent-atlas-foundation-depth` | `content_and_depth` | `Module Review` | The profile-defined foundation pages in one bounded module satisfy their registered depth predicates. | `emits` | `profiles/examples/agent-atlas/scope-and-architecture.md#Foundation Depth Requirements` |
| `agent-atlas-interview-readiness-acceptance` | `interview` | `Single Note Review` | One Interview Card and its bound canonical topics presented for `interview-ready` promotion satisfy the registered readiness predicate. | `emits` | `profiles/examples/agent-atlas/interview/interview-review-and-acceptance.md#Interview Readiness Acceptance` |
| `agent-atlas-profile-wide-interview-acceptance` | `interview` | `Specialized Audit` | The complete in-scope Agent Systems Atlas snapshot satisfies the registered profile-wide Interview-layer acceptance predicate. | `emits` | `profiles/examples/agent-atlas/interview/interview-review-and-acceptance.md#Profile-wide Interview Acceptance` |
| `agent-atlas-interview-residual-disposition` | `coverage_and_integration` | `Batch Review` | The merged in-scope snapshot's Interview-answer residual candidates outside `Interview Preparation/` all have an accepted disposition. | `emits` | `profiles/examples/agent-atlas/interview/interview-review-and-acceptance.md#Residual-content Disposition` |
