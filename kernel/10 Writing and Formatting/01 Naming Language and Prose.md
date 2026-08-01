## Navigation

- Parent: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Next: [[kernel/10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].

## Purpose

本标准定义文件命名、标题结构、段落和列表。reader-facing language、identity 保留边界及显示顺序由所选 profile 的 `Language Contract` 单独维护。

## Naming

- 文件夹和文件名使用由所选 profile 的 `Language Contract` 注册的 canonical identity。
- 文件名使用行业最常见正式名称。
- 缩写与全称通过 aliases 处理，不创建重复文件。
- 不在文件名中添加日期，除非文件本质是日志或时间记录。
- 不使用含义模糊的名称，例如 `Notes`、`Basics 2`、`Advanced Stuff`。
- Overview、Sequence Guide、Checklist、Cheat Sheet、Expression Layer Artifact 等类型在文件名中明确表达。
- Source Note 文件名应识别 organization / author 与来源主题，例如 `Example Organization - Reliable Distributed Systems`；publication date 放 metadata，不默认放文件名。
- Research Synthesis 使用研究问题或现象命名，不使用某一篇文章标题，也不在结论未稳定时伪装成 canonical Term Note。

## Language Routing（语言规则路由）

- 所有正文、标题、表格、图表、Source Note 和 `Expression Layer Artifact` 的 reader-facing language 选择，统一读取所选 profile 的 `Language Contract`。
- 具体显示顺序、identity 保留值和例外边界由 `Language Contract` 提供。
- 一个问题只能有一个 canonical owner；其它规则通过 slot 引用语言合同，不能复制一份略有不同的政策。
- 本页不复制语言政策，避免 Naming、Terminology、Expression Layer 和 Formatting 产生多个 owner。

通用决策骨架：

```text
Machine-consumed identifier? -> preserve exact identity
External identity or official name? -> preserve exact identity
Selected Language Contract has an unambiguous reader-facing form? -> use that form
Identity preservation is required? -> use the Language Contract display form
Otherwise -> use the Language Contract default prose form
```

## Titles

- 不重复显示文件名和 H1。
- 默认从 `## Definition`、`## Purpose` 或内容需要的首个二级标题开始。
- 不在普通知识页显示日期、主题、今日交付等冗余字段。
- Heading 应稳定、明确，并考虑 heading links。
- 同一层级标题使用一致语义，不混用过多同义标题。
- reader-facing 标题的显示顺序与文件名注释边界由所选 profile 的 `Language Contract` 约束。

### Stable Heading Migration

当 `Language Contract` 的 display change 会改变已有 heading anchor 时，必须先盘点 incoming heading links，再原子更新 heading 与引用，运行 missing / ambiguous / heading resolution 检查并记录 migration evidence。当前 batch 无法安全迁移时保留旧 heading、登记 Required repair，不得静默断开引用或把临时兼容状态宣告为最终合规。

## Paragraphs And Lists

- 段落负责解释因果和机制，列表负责枚举，不用列表代替全部推理。
- 每个 section 不能长期只有一句话。
- 避免连续多个只有名词和短句的 bullet list。
- 比较多个方案时使用统一维度，而不是各写一段不对称描述。
- 复杂层级优先拆 section，避免过深 nested bullets。
