## Navigation

- Parent: [[kernel/K04 Content Depth Standard|K04 Content Depth Standard]].
- Previous: [[kernel/K04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]].
- Next: [[kernel/K04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].

## System Design Structure

A system design page SHOULD usually include:

```text
Goals And Non-goals
Functional Requirements
Non-functional Requirements
Architecture
Core Components
End-to-end Flow
API And Data Contracts
State And Lifecycle
Concurrency And Scheduling
Coordination And Handoff
Evidence And Verification Path
Failure Handling
Reliability
Recovery And Rollback
Security And Permissions
Observability
Scalability
Latency And Cost
Alternatives And Tradeoffs
Worked Scenario
Expression Layer Link
Sources
```

## Production System Reasoning

P0 / P1 pages covered by the `Production System Reasoning Applicability` register entry of the selected profile MUST be able to answer enterprise-system follow-up questions along five paths:

- Execution path: how a goal becomes a result through decisions, tools, and the environment.
- State path: who owns, stores, updates, synchronizes, and cleans up state.
- Coordination path: how tasks are split, handed off, parallelized, merged, and how conflicts are handled.
- Evidence path: how conclusions, metrics, and success judgments are produced and verified.
- Recovery path: after failure, how to retry, resume, fallback, rollback, compensate, or hand over to a human.

A page MUST NOT draw only the happy-path architecture. Each path states at least the key contracts, observable signals, failure propagation, and control points.

The division of labor between Process / Flow and System Design is: the former owns ordered transitions and control semantics; the latter owns the complete component architecture and cross-flow constraints. The two link to each other, but the junction MUST NOT be resolved by repeating the same full passage of content.

Vague expressions such as "Backup" MUST be broken down into actual mechanisms: data backup, checkpoint, durable execution, failover, fallback, rollback, compensating transaction, or human takeover.
