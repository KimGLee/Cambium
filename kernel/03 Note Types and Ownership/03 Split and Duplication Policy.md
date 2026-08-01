## Navigation

- Parent: [[kernel/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Previous: [[kernel/03 Note Types and Ownership/02 Ownership and Canonical Notes|Ownership and Canonical Notes]].

## Purpose

本模块是页面生命周期政策（Split Merge and Retirement Policy）的 canonical owner，覆盖拆分、合并与退役。文件名保持不变以避免断链。

## When To Split A Note

满足以下情况时考虑拆分：

- 子主题被多个页面复用。
- 子主题有独立机制、公式、生命周期或失败模式。
- 当前页面因解释该子主题而偏离主线。
- 子主题能产生独立的学习问题或所选 profile 注册的表达问题。
- 拆分后仍能通过明确承接关系保持连贯。
- 新来源揭示了多个具有不同 owner 的独立知识对象。

## When Not To Split

- 只有一句普通定义。
- 只在当前页面使用。
- 拆分后新页面只有两三句话。
- 子主题必须依赖当前页面上下文才能理解。
- 只是为了增加图谱节点或文件数量。
- 只是某篇文章使用的临时标签，尚未证明具有稳定、可复用含义。

## Duplication Policy

允许重复：

- 为保证段落可读而提供的一句上下文解释。
- 受限长度表达中的最小必要定义。
- Case Study 中对决策背景的简短复述。
- Research Synthesis 中为比较来源而提供的最小 claim 摘要。

不允许重复：

- 多个页面复制同一整段机制说明。
- 多个 profile 表达产物保存同一个完整答案。
- Roadmap 或 Cheat Sheet 重新撰写知识页正文。
- 通过改名制造实际相同的概念页。

## Retirement

退役不删除文件：

- Frontmatter 设置 `lifecycle: retired`。
- 正文顶部加入 tombstone 块：退役原因、退役日期、`superseded_by` 链接指向接替页；没有接替页时说明原因。
- 从 coverage 的 Required 集合移除。
- 退役 gate 硬条件：先运行 `Tools/check_links.py` 找出全部入链，并逐条改指到接替页，之后才能退役。
- 高入度页面退役的入链改指工作，按所选 profile 未覆写时的内核默认值“改指数 ÷ 6”折算为页数计入维护轮预算（规则 owner：[[kernel/00 Standards Control/02 Task Routing and Pre-execution|00/02]] Maintenance Run Envelope，此处引用）；profile 可以显式覆写该折算参数。

## Merge

- 处置优先序：确认重复后，**合并义务优先**于其它处置；不得以授权缺失为由搁置已确认的重复。
- 被并页按 Retirement 的 tombstone 与入链改指流程处理，`superseded_by` 指向合并后页面。
- 合并后页面必须吸收被并页的独有内容与 Sources，不得静默丢弃。
- 被并页含无法确认来源的修改时：独有内容一律全部吸收进 canonical 页，并在 tombstone 中记录来源不明段落的原文位置与吸收去向——保全的是内容，而非保留页面本身。
- 合并与退役不需要逐条 governance 授权；仅**物理删除文件**需要 governance 授权。

## Downgrade And Subtree Deprecation

- priority 下调不走退役流程，把理由记入 Ledger 即可。
- 整个技术分支过时时，按依赖顺序自底向上批量退役，作为维护批次的一种类型执行。

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[kernel/05 Terminology Standard|Terminology Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
