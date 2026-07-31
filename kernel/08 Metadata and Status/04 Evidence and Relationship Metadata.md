## Navigation

- Parent: [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Previous: [[kernel/08 Metadata and Status/03 Status Axes|Status Axes]].
- Next: [[kernel/08 Metadata and Status/05 Review Source and Migration Metadata|Review Source and Migration Metadata]].

## Evidence Maturity

`authoring_status` 表示页面写作与审阅进度；`evidence_maturity` 表示时效性或经验性结论的证据强度。两者不能互相替代。

旧页面中的 `status` 字段在迁移期间视为 `authoring_status` 的兼容别名，不再用于表达 profile readiness 或学习状态。

允许值：

- `signal`：值得调查，但尚无充分证据。
- `single-source`：有一个可追踪来源支持。
- `corroborated`：多个相互独立来源支持关键观察。
- `validated`：存在可靠实验、复现或稳定生产证据。
- `contested`：可信来源之间存在实质冲突。
- `superseded`：结论已被更新证据或更准确的解释取代。

稳定数学定义通常不需要 `evidence_maturity`。前沿系统 / 运行控制模式、行业经验、benchmark 结论和 Research Synthesis 应填写。

一篇 Source Note 可以是 `authoring_status: reviewed`，同时仍然只有 `evidence_maturity: single-source`。这表示来源记录准确，不表示其结论已经普遍成立。

## Prerequisites

- 只记录真正必须先理解的内容。
- 使用 canonical note 路径或稳定名称。
- 不把所有 Related links 都放进 prerequisites。
- 循环依赖需要人工检查。

## Aliases

Aliases 用于：

- 英文全称和缩写。
- `Language Contract` 注册的其它语言常用名称。
- 行业常用替代拼写。

Aliases 不能用来掩盖两个实际不同的概念。
