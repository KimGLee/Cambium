## Navigation

- Parent: [[Knowledge Base Standards/00 Standards Overview|00 Standards Overview]].
- Previous: [[Knowledge Base Standards/00 Standards Control/03 Standards Governance|Standards Governance]].
- Next: [[Knowledge Base Standards/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]].

## Control State Separation

| State | Owner | Meaning | Must Not Be Used As |
|---|---|---|---|
| `task_state` | Progress Ledger | planned、active、paused、blocked、completion-candidate、complete、cancelled | 页面内容质量 |
| `authoring_status` | Coverage Ledger / page metadata | unassessed、outline、drafted、reviewed | 用户学习进度或证据强度 |
| `interview_status` | Coverage Ledger / Interview Preparation | missing、mapped、drafted、reviewed、interview-ready、not-required | canonical note 深度 |
| `evidence_maturity` | Canonical / Source / Synthesis note | signal、single-source、corroborated、validated、contested、superseded | 写作是否完成 |
| `learning_status` | User learning workflow | not-started、learning、self-tested、mastered | 知识库建设进度 |

本表为控制面速览；完整词表以各 owner 为准：task_state 见 [[Knowledge Base Standards/02 Build Execution/01 Contract Time and Task State|02/01]]，其余各轴见 [[kernel/08 Metadata and Status/03 Status Axes|08/03]]。

`coverage_disposition` 另外说明页面在当前 scope 中是 required、optional、deferred 还是 excluded。

## Scope

本标准适用于以下知识体系：

- `Modeling Fundamentals`
- `Machine Learning Knowledge`
- `Deep Learning Knowledge`
- `LLM Knowledge`
- `Agent Knowledge`
- `AI Systems Engineering`
- `Knowledge Sources`
- `Research Synthesis`
- `Industry Cases`
- `Interview Preparation`
- `Knowledge Base Management`
- 后续新增的共享基础、评估、安全和治理体系

知识库以 Agent 和 Harness 为组织主线，但完整保留 Modeling、ML、DL、LLM、Retrieval 和 RAG 基础。基础层负责可复用机制，Agent/Harness 层负责把这些机制连接成可执行、可控制、可评估的生产系统。

明确排除：`Python Algorithm Agent Training`。除非用户以后单独授权，不迁移、不重构、不纳入本轮质量验收。

`Knowledge Base Standards` 属于控制面，不计入普通内容建设成果。只有单独授权的 governance task 可以修改。
