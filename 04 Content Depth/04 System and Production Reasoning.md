## Navigation

- Parent: [[Knowledge Base Standards/04 Content Depth Standard|04 Content Depth Standard]].
- Previous: [[Knowledge Base Standards/04 Content Depth/03 Process and Flow Structure|Process and Flow Structure]].
- Next: [[Knowledge Base Standards/04 Content Depth/05 Source and Evaluation Depth|Source and Evaluation Depth]].

## System Design Structure

系统设计页面通常应包含：

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
Interview Preparation Link（面试准备链接）
Sources（来源）
```

## Production System Reasoning

P0 / P1 Agent、Harness 和 AI Systems 页面必须能够沿五条链路回答企业系统追问：

- Execution path：目标如何经过决策、工具和环境变成结果。
- State path：状态由谁拥有、保存、更新、同步和清理。
- Coordination path：任务如何拆分、交接、并行、合并和处理冲突。
- Evidence path：结论、指标和成功判断如何产生并被验证。
- Recovery path：失败后如何 retry、resume、fallback、rollback、compensate 或转人工。

页面不能只画 happy-path architecture。每条链路至少说明关键 contract、可观测信号、失败传播和控制点。

Process / Flow 和 System Design 的分工是：前者拥有有序 transition 和控制语义，后者拥有完整组件架构及跨流程约束。二者互相链接，但不能通过重复同一整段内容解决衔接。

“Backup”之类的模糊表达必须拆成实际机制：data backup、checkpoint、durable execution、failover、fallback、rollback、compensating transaction 或 human takeover。
