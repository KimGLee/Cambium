# Priority Rubric

Interface: [Priority Rubric slot](../../README.md#priority-rubric-slot)

## Profile-owned Grant Criteria

| Priority | Testable grant predicate (`No grants` if always false) | Protected reader capability or time horizon (`Not applicable` for no grants) |
|---|---|---|
| `P0` | The page has `coverage_disposition: required` and either (a) is named as a canonical entry in `Knowledge Base Management/Competency Matrix.md#P0 Competencies`, or (b) is the sole canonical contract for goal/plan, context/state, tool effects, permission/policy, completion/recovery, evaluation evidence, or production operation used by at least two recorded P0 competencies. The supporting entry or dependency edges must be recorded in the Competency Matrix or the [Atlas content-planning register](scope-and-architecture.md#atlas-content-planning-register-boundary). | The reader can design, execute, verify, diagnose, and recover the end-to-end Agent/Harness control path without a missing canonical owner. |
| `P1` | The page is not P0, has `coverage_disposition: required`, and at least one is recorded: it is a direct prerequisite of a P0 owner; it is a canonical mechanism reused by two registered logical layers; it supplies current source, synthesis, or case evidence needed to validate a P0 claim; or it is a target-role topic named by the Competency Matrix and requires an Interview artifact. | The reader can defend important alternatives, foundations, evidence, and production tradeoffs during the current corpus revision and interview-preparation horizon. |
