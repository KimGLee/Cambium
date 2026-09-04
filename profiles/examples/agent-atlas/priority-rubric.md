# Priority Rubric

Kernel owner: K00/07. Common slot identity is registered in the Kernel Profile interface.

## Profile-owned Grant Criteria

| Priority | Testable grant predicate (`No grants` if always false) | Protected reader capability or time horizon (`Not applicable` for no grants) |
|---|---|---|
| `P0` | The page's exact repository-relative path appears in `canonical_markdown_paths` for at least one `P0` capability in the Profile-bound Capability Matrix, and that capability is necessary to satisfy a declared Atlas goal. If a page qualifies for both P0 and P1, P0 takes precedence. | The reader can understand, design, verify, operate, diagnose, and recover the core end-to-end Agent and Harness system described by Atlas. |
| `P1` | The page is not P0 and its exact repository-relative path either appears in `canonical_markdown_paths` for a `P1` capability, appears in `evidence_paths` for a `P0` capability, or is the canonical page of a Global Map entry whose typed dependency directly feeds an entry used by a `P0` capability through `prerequisite-for`, `evidence-input-to`, `control-input-to`, `system-input-to`, or `canonical-source-for`. A derived Expression artifact or its readiness is not a grant condition. | The reader can explain and defend the mechanisms, prerequisites, evidence, tradeoffs, failure modes, safety boundaries, and evaluation methods that directly support those core capabilities. |

## Priority Quota

- Registration: None

| Class | Maximum corpus share | Rationale |
|---|---|---|
