## Navigation

- Parent: [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Previous: [[kernel/08 Metadata and Status/04 Evidence and Relationship Metadata|Evidence and Relationship Metadata]].

## Review Dates

- `last_reviewed`：最近一次内容质量审阅。
- `last_verified`：最近一次对时效性外部事实的核验。

稳定数学概念不需要频繁更新 `last_verified`，协议、价格、产品和安全要求需要。

`first_seen` 记录 emerging topic 或 source signal 首次进入知识库的日期，不等同于来源发布时间。

## Freshness And Review Due

`volatility` 使用受控词表，描述页面结论的时效衰减速度：

- `fast`：快变内容，如外部服务与接口现状、组件对比、性能数字；复验间隔 120 天。
- `slow`：慢变内容，如方法论和系统设计模式；复验间隔 365 天。
- `stable`：稳定内容，如数学和经典基础原理；不设复验截止。

未显式声明时按所选 profile 的 `Vocabulary Extensions` 所登记的 domain 派发表取默认值，单页可显式覆盖。

`review_by` 不手工填写，由 `Tools/check_freshness.py` 按 `last_verified + 对应间隔` 计算；页面没有 `last_verified` 时以创建日期或最近一次实质修改日期代替，并标记为待首验。

过期语义：`review_by` 已过表示页面进入维护轮候选清单（按 priority 排序），不自动改变页面的任何状态轴。

复验时必须回答：该主题今天是否仍配当前 priority？升降级记入 Coverage Ledger 并注明理由。

## Conditional Source Metadata

Source Note 和 Research Synthesis 可以增加：

```yaml
source_type: official-engineering-article
source_organization: Example Organization
source_date:
source_url:
evidence_roles:
  - implementation-evidence
claim_scope:
supersedes:
superseded_by:
review_due:
```

- `source_type` 使用受控词表，区分 paper、official article、documentation、benchmark、postmortem、community discussion 和 independent reproduction。
- `evidence_roles` 描述来源承担的证据作用，而不是简单重复来源权威级别。
- `claim_scope` 说明结论适用于哪个组件、execution / control setup、任务、组织或时间范围。
- `supersedes` / `superseded_by` 保留结论演化关系。
- `review_due` 用于快速变化内容，不要求稳定基础知识频繁复审。

## Migration Rules

- 先批准 schema，再批量添加 frontmatter。
- 先在 Coverage Ledger 中建立权威状态，再决定是否批量写回 Frontmatter。
- 迁移时不改变正文语义。
- 旧 `status` 只迁移到 `authoring_status`；不得据此推断 profile 注册的表达就绪状态、`learning_status` 或 `evidence_maturity`。
- 没有 Frontmatter 的现有页面默认是 `unassessed`，不是 `drafted` 或 `reviewed`。
- aliases 和 prerequisites 需要人工或半自动审阅。
- 不一次性把所有页面标记为 reviewed。
- `deferred` 和 `excluded` 必须有明确原因，不能作为隐藏缺口的默认值。
- 完成后验证所选 knowledge host 的插件和 relationship graph 不受影响。

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- [[Knowledge Base Standards/02 Knowledge Base Build Execution Standard|Knowledge Base Build Execution Standard]]
