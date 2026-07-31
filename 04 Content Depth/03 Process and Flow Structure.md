## Navigation

- Parent: [[Knowledge Base Standards/04 Content Depth Standard|04 Content Depth Standard]].
- Previous: [[Knowledge Base Standards/04 Content Depth/02 Core Concept Structure|Core Concept Structure]].
- Next: [[Knowledge Base Standards/04 Content Depth/04 System and Production Reasoning|System and Production Reasoning]].

## Process And Flow Structure

Process / Flow 页面需要解释“系统如何推进”，不能只罗列步骤名称。通常应覆盖：

```text
Position And Scope（位置与范围）
Goal And Exit Criteria（目标与退出标准）
Actors And Authority（参与角色与权限）
Inputs And Preconditions（输入与前置条件）
Initial State（初始状态）
Happy Path（正常路径）
Decision Points（决策点）
Branches And Fallbacks（分支与回退）
Loop And Replanning Conditions（循环与重规划条件）
State Transitions（状态转换）
External Effects And Receipts（外部效果与凭据）
Retry / Timeout / Cancel / Pause（重试 / 超时 / 取消 / 暂停）
Human Approval Or Handoff（人工审批或交接）
Failure Propagation And Recovery（失败传播与恢复）
Stop Condition And Terminal Proof（停止条件与终态证明）
Observability And Evaluation（可观测性与评估）
Worked Execution Trace（完整执行追踪）
Related Component Contracts（相关组件契约）
Interview Preparation Link（面试准备链接）
Sources（来源）
```

Process / Flow 页面至少区分以下角色：

- Model proposal：模型建议下一动作、参数或解释。
- Harness control：验证、授权、调度、预算、状态提交和完成判断。
- External executor：工具、服务、数据库、filesystem、browser 或其它环境实际产生效果。
- Human authority：在高风险、歧义或策略要求下批准、拒绝、修改或接管。

并非每个流程都需要四类角色，但不能把模型“提出动作”写成模型已经直接执行了外部效果。

流程图只是结构视图，正文还必须解释：

- 每个关键 transition 为什么存在。
- branch 和 loop 的触发条件。
- authoritative state 在哪里提交。
- timeout 后结果是 failed、unknown 还是已经产生副作用。
- stop condition 和 completion verification 是否由同一个主体判断。
- 失败如何被检测、归因、恢复和审计。

重要 Process / Flow Note 至少包含一个 worked trace，从具体输入沿状态、决策、工具结果和 Terminal Proof 走完一次执行；还应包含一个 failure trace，展示流程在哪一步偏离以及如何恢复。
