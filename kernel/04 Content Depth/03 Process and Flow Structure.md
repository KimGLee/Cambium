## Navigation

- Parent: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Previous: [[kernel/04 Content Depth/02 Core Concept Structure|Core Concept Structure]].
- Next: [[kernel/04 Content Depth/04 System and Production Reasoning|System and Production Reasoning]].

## Process And Flow Structure

A Process / Flow page needs to explain "how the system advances"; it MUST NOT merely list step names. It SHOULD usually cover:

```text
Position And Scope
Goal And Exit Criteria
Actors And Authority
Inputs And Preconditions
Initial State
Happy Path
Decision Points
Branches And Fallbacks
Loop And Replanning Conditions
State Transitions
External Effects And Receipts
Retry / Timeout / Cancel / Pause
Approval Or Handoff
Failure Propagation And Recovery
Stop Condition And Terminal Proof
Observability And Evaluation
Worked Execution Trace
Related Component Contracts
Expression Layer Link
Sources
```

A Process / Flow page answers at least the following four role questions:

- `proposer`: who proposes the next action, parameters, or interpretation.
- `gatekeeper`: who validates, authorizes, schedules, controls budget, commits state, and judges completion.
- `executor`: who actually produces effects in the external environment.
- `stopper`: who approves, rejects, modifies, takes over, or halts under high risk, ambiguity, or policy requirements.

The four questions do not require four distinct actors; the same actor MAY hold multiple roles. The selected profile MAY add roles, but MUST NOT lower the four-question floor. A proposer "proposing an action" MUST NOT be written as the executor having actually produced an external effect.

A flow diagram is only a structural view; the body MUST additionally explain:

- Why each key transition exists.
- The trigger conditions of branches and loops.
- Where authoritative state is committed.
- Whether the result after a timeout is failed, unknown, or a side effect has already been produced.
- Whether the stop condition and completion verification are judged by the same actor.
- How failures are detected, attributed, recovered, and audited.

An important Process / Flow Note contains at least one worked trace that walks one execution from concrete inputs through states, decisions, tool results, and the Terminal Proof; it SHOULD also contain a failure trace showing at which step the flow deviates and how it recovers.
