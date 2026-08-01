## Navigation

- Parent: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Previous: [[kernel/04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]].
- Next: [[kernel/04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].

## System Design Structure

A system design page SHOULD usually include:

```text
Goals And Non-goals（目标与非目标）
Functional Requirements（功能性需求）
Non-functional Requirements（非功能性需求）
Architecture（架构）
Core Components（核心组件）
End-to-end Flow（端到端流程）
API And Data Contracts（API 与数据契约）
State And Lifecycle（状态与生命周期）
Concurrency And Scheduling（并发与调度）
Coordination And Handoff（协调与交接）
Evidence And Verification Path（证据与验证路径）
Failure Handling（失败处理）
Reliability（可靠性）
Recovery And Rollback（恢复与回滚）
Security And Permissions（安全与权限）
Observability（可观测性）
Scalability（可扩展性）
Latency And Cost（延迟与成本）
Alternatives And Tradeoffs（替代方案与权衡）
Worked Scenario（完整场景推演）
Expression Layer Link（表达层链接）
Sources（来源）
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
