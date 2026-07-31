## Navigation

- Parent: [[Knowledge Base Standards/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Previous: [[Knowledge Base Standards/08 Metadata and Status/02 Scope Level Depth and Priority|Scope Level Depth and Priority]].
- Next: [[Knowledge Base Standards/08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]].

## Status Axes

`authoring_status`、`interview_status`、`evidence_maturity` 和 `learning_status` 是四个独立维度，不能合并成一条状态链。

例如，一个页面可以同时满足：

```yaml
authoring_status: reviewed
interview_status: missing
evidence_maturity: single-source
learning_status:
```

这表示知识页已经完成写作审阅，但面试材料尚未建立，经验性结论仍只有单一来源，用户学习状态未知。

文件存在、Wiki link 可解析、Roadmap checkbox 存在或页面字数较多，都不能自动改变任一状态。

### Authoring Status

`authoring_status` 只表示知识文件的写作与质量审阅进度：

- `unassessed`：旧页面或新纳入范围的页面尚未按当前 Standards 审阅。没有 metadata 的既有页面在 Coverage Ledger 中默认归入此状态。
- `outline`：只有标题、结构或零散要点，不算内容完成。
- `drafted`：主要内容已经写入，但事实、公式、链接、来源、面试迁移或渲染尚未全面检查。
- `reviewed`：通过对应 note type 的内容、来源、公式、链接、重复性、格式和必要渲染检查。

状态转换为：

```text
unassessed
 -> outline
 -> drafted
 -> reviewed
```

发现回归、来源失效或重大结构缺口时，`reviewed` 可以降回 `drafted`。不能因为文件存在、篇幅达到阈值或自动检查通过而直接升级。

### Interview Status

`interview_status` 只表示独立面试材料的覆盖情况：

- `not-required`：该主题按 [[Knowledge Base Standards/11 Interview Content Standard|Interview Content Standard]] 不需要独立 Interview Card。
- `missing`：P0 / P1 主题需要 Interview Card，但尚未建立映射。
- `mapped`：已确定目标 Interview Card，但内容尚未完成。
- `drafted`：Interview Card 已写入，尚未完成 Interview Review。
- `reviewed`：Interview Card 已通过内容和双语审阅。
- `interview-ready`：知识页已 `reviewed`，Interview Card、追问、评分信号和自测均达到验收标准。

知识页和 Interview Card 可以拥有不同的 `authoring_status`。知识页中的一个链接不能自动把主题升级为 `interview-ready`。

### Learning Status

`learning_status` 属于用户个人学习进度，不由批量知识库建设自动写入：

- `not-started`
- `learning`
- `self-tested`
- `mastered`

`mastered` 需要口述、自测、实践或用户明确确认。Roadmap checkbox 和 `learning_status` 不能用于证明页面写作完成。

### Coverage Disposition

`coverage_disposition` 表示页面在当前建设范围中的处理方式：

- `required`：当前范围内必须完成；未达到目标状态时阻止 task completion。
- `optional`：有价值但不阻断当前任务。
- `deferred`：当前暂缓，必须填写 `deferred_reason`、重新进入条件或目标批次。
- `excluded`：明确不属于当前任务，必须能回溯到 scope contract。

`next_batch` 用于把未完成页面映射到明确批次，不能只写模糊的“以后补充”。Coverage disposition 的权威汇总保存在 Coverage Ledger；Frontmatter 只是页面本地投影。
