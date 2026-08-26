# Priority Rubric

Interface: [Kernel-owned Profile interface](../../../kernel/K00%20Standards%20Control/19%20Profile%20Extension%20Interface.md) — Priority Rubric slot

## Profile-owned Grant Criteria

| Priority | Testable grant predicate (`No grants` if always false) | Protected reader capability or time horizon (`Not applicable` for no grants) |
|---|---|---|
| `P0` | The page is named as a canonical path by a `P0` capability in the Capability Matrix, and a volunteer cannot reach that capability's finish condition without it. | A trained volunteer completes a member's service unattended in the session it was booked for. |
| `P1` | The page is named by a `P1` capability, or it is the source note a `P0` capability quotes its published figures from. | The workshop can still stand behind a quoted figure at the next service, up to one document revision later. |

P2 remains the kernel fallback for every other in-scope page. This rubric grants priority to pages; it does not rank the corpus capabilities themselves, which carry their own `priority` field in the Capability Matrix.

## Priority Quota

- Registration: Configured

| Class | Maximum corpus share | Rationale |
|---|---|---|
| `P0` | `10%` | A service corpus keeps its always-verified core deliberately small; ten percent of the pages carry the procedures a mechanic opens with a customer waiting |
| `P1` | `35%` | The kernel default fits the applied middle tier as measured |
