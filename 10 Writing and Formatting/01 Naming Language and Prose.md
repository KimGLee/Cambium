## Navigation

- Parent: [[Knowledge Base Standards/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Next: [[Knowledge Base Standards/10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].

## Purpose

本标准定义文件命名、标题结构、段落和列表。中文优先表达、英文保留边界及
双语显示顺序由 [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|Chinese-first Technical Language]] 单独维护。

## Naming

- 文件夹和文件名使用英语。
- 文件夹和文件名不添加中文翻译、中文注释或双语后缀。
- 文件名使用行业最常见正式名称。
- 缩写与全称通过 aliases 处理，不创建重复文件。
- 不在文件名中添加日期，除非文件本质是日志或时间记录。
- 不使用含义模糊的名称，例如 `Notes`、`Basics 2`、`Advanced Stuff`。
- Overview、Roadmap、Checklist、Cheat Sheet、Interview Card 等类型在文件名中明确表达。
- Source Note 文件名应识别 organization / author 与来源主题，例如 `Anthropic - Effective Harnesses for Long-running Agents`；publication date 放 metadata，不默认放文件名。
- Research Synthesis 使用研究问题或现象命名，不使用某一篇文章标题，也不在结论未稳定时伪装成 canonical Term Note。

## Language Routing（语言规则路由）

- 所有正文、标题、表格、图表、Source Note 和 Interview Card 的语言选择，统一读取
  [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|Chinese-first Technical Language]]。
- 双语显示只允许 `English Term（中文注释）`，不允许 `中文注释（English Term）`。
- 本页不复制语言政策，避免 Naming、Terminology、Interview 和 Formatting 产生多个 owner。

## Titles

- 不重复显示文件名和 H1。
- 默认从 `## Definition（定义）`、`## Purpose（目的）` 或内容需要的首个二级标题开始。
- 不在普通知识页显示日期、主题、今日交付等冗余字段。
- Heading 应稳定、明确，并考虑 heading links。
- 同一层级标题使用一致语义，不混用过多同义标题。
- 标题的中英文显示顺序由
  [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language#Headings And Titles（标题）|Headings And Titles]]
  约束；文件名本身不需要中文注释。

## Paragraphs And Lists

- 段落负责解释因果和机制，列表负责枚举，不用列表代替全部推理。
- 每个 section 不能长期只有一句话。
- 避免连续多个只有名词和短句的 bullet list。
- 比较多个方案时使用统一维度，而不是各写一段不对称描述。
- 复杂层级优先拆 section，避免过深 nested bullets。
