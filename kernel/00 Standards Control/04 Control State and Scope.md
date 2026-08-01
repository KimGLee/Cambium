## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/03 Standards Governance|Standards Governance]].
- Next: [[kernel/00 Standards Control/05 Core Principles and Standards Map|Core Principles and Standards Map]].

## Control State Separation

| State | Owner | Meaning | Must Not Be Used As |
|---|---|---|---|
| `task_state` | Progress Ledger | planned、active、paused、blocked、completion-candidate、complete、cancelled | 页面内容质量 |
| `authoring_status` | Coverage Ledger / page metadata | unassessed、outline、drafted、reviewed | 用户学习进度或证据强度 |
| `Expression Status Axis` | Selected profile registry | 由所选 profile 注册的表达产物 coverage 与 readiness 取值 | canonical note 深度 |
| `evidence_maturity` | Canonical / Source / Synthesis note | signal、single-source、corroborated、validated、contested、superseded | 写作是否完成 |
| `learning_status` | User learning workflow | not-started、learning、self-tested、mastered | 知识库建设进度 |

本表为控制面速览；完整词表以各 owner 为准：task_state 见 [[kernel/02 Build Execution/01 Contract Time and Task State|02/01]]，其余 kernel 轴见 [[kernel/08 Metadata and Status/03 Status Axes|08/03]]，表达状态值由 `Expression Status Axis` role 提供。

`coverage_disposition` 另外说明页面在当前 scope 中是 required、optional、deferred 还是 excluded。

## Scope

本标准适用于由所选 `Profile Scope` 明确登记、并采用本控制面的知识语料范围。具体目标、知识结构、内容目录与扩展范围由该 role 提供，kernel 不固化部署清单。

明确排除项必须写入 `Excluded Scope` slot；未登记排除项时该 slot 也必须显式为空。迁移、重构或验收不得越过当前 task contract 与该 slot，任何范围变化都需要相应授权。

Kernel Standards 属于控制面，不计入普通内容建设成果。只有单独授权的 governance task 可以修改；普通内容任务必须把它作为只读保护范围。
