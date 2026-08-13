# Priority Rubric

Interface: [Priority Rubric slot](../README.md#priority-rubric-slot)

## Profile-owned Grant Criteria

Every in-scope page stays at the kernel P2 fallback until this profile
registers a grant predicate. Open grants later, through ordinary Standards
adoption, when a page protects a reader capability or deadline that the
uniform fallback does not.

| Priority | Testable grant predicate (`No grants` if always false) | Protected reader capability or time horizon (`Not applicable` for no grants) |
|---|---|---|
| `P0` | No grants | Not applicable |
| `P1` | No grants | Not applicable |

## Priority Quota

The standing quota targets this corpus holds its P0/P1 shares to. K00/07 owns
the quota model; `None` selects its kernel defaults (P0 <=15%, P1 <=35%).
Register `Configured` with both classes when this corpus's own structure
justifies different standing targets -- the rationale column is required,
because a quota without a recorded reason is indistinguishable from a quota
nobody chose. The two shares together stay strictly below 100: P2 is the
remainder class and carries every terminology stub and placeholder page. A
temporary excess is not registered here -- it is a bounded contract policy
exception via `apply_contract_amendment.py`, and it dies with the task.

- Registration: None

| Class | Maximum corpus share | Rationale |
|---|---|---|
