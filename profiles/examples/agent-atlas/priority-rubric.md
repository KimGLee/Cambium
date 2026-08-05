# Priority Rubric

Interface: [Priority Rubric slot](../../README.md#priority-rubric-slot)

## Profile-owned Grant Criteria

| Priority | Testable grant predicate (`No grants` if always false) | Protected reader capability or time horizon (`Not applicable` for no grants) |
|---|---|---|
| `P0` | The page has `coverage_disposition: required` and either (a) its canonical path supports a bound [Capability Matrix](corpus-planning.yaml) row whose `Priority` is `P0`, or (b) it is the sole canonical contract for goal/plan, context/state, tool effects, permission/policy, completion/recovery, evaluation evidence, or production operation used by at least two Matrix capabilities whose `Priority` is `P0`. The path must be a Global Map Entry, and every prerequisite or downstream relation used by this grant must be an explicit Global Map Typed Dependency rather than an inferred link. | The reader can design, execute, verify, diagnose, and recover the end-to-end Agent/Harness control path without a missing canonical owner. |
| `P1` | The page is not P0, has `coverage_disposition: required`, and at least one is recorded: its canonical path supports a Matrix row whose `Priority` is `P1`; a Global Map Typed Dependency makes it a direct prerequisite of a P0 owner; it is a canonical mechanism reused by two registered logical layers; it supplies current source, synthesis, or case evidence needed to validate a P0 capability; or it is a target-role topic in the Matrix that requires an Interview artifact. | The reader can defend important alternatives, foundations, evidence, and production tradeoffs during the current corpus revision and interview-preparation horizon. |
