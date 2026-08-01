## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel content-depth contract: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].
- Kernel writing contract: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Kernel writing predecessor: [[kernel/10 Writing and Formatting/04 Rendering and Formatting Review|Rendering and Formatting Review]].

## Content Length Unit

- Kernel unit role: `profile 定义的内容长度单位`
- Agent Atlas value: `中文字`
- Conversion: 一个单位按一个中文字计。
- Range policy: 使用 kernel 的数值范围，不做覆写。

## Terminology Naming And Aliases

- 文件名使用最常用的英文正式名称或行业通用缩写。
- 全称、缩写、同义词、中英文名放入 `aliases`。

示例：

```yaml
type: term
domain: ai-systems
scope: shared
aliases:
  - Idempotent
  - 幂等性
```

## Alias Language Extension

- 常见中文名称。

## Display Language Contract（显示语言契约）

- canonical 文件名保持英文，不向文件名追加中文注释。
- 首次有意义出现的链接保留英文 identity，中文解释放在括号内：
  `[[Idempotency]]（幂等性）`。
- 双语显示只允许 `English Term（中文注释）`，不允许 `中文注释（English Term）`。
- aliases 可以同时保存英文全称、缩写和中文同义词，但 alias metadata 不改变正文显示顺序。
- 具体标题、正文、表格、图表、Source 和 Interview 例外由下列 Language Contract sections 统一维护。

## Terminology Kernel Binding

- Kernel owner: [[kernel/05 Terminology/03 Naming Context and Linking|Naming Context And Linking]]

## Writing And Formatting Integration

- Kernel contract: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Canonical profile sections: `Purpose（目的）`、`Ownership Boundary（职责边界）`、`File And Folder Names（文件与文件夹名称）`、`Headings And Titles（标题）`、`Protected English Tokens（受保护英文标识）`、`Body Prose（正文）`、`Tables（表格）`、`Diagrams Schemas And Code（图表结构与代码）`、`Source And Interview Exceptions（来源与面试例外）`、`Terminology And Wiki Links（术语与链接）`、`Acceptance And Audit（验收与审计）`、`Migration And Invalidation（迁移与失效）`、`Examples（示例）`、`Related（相关规则）`.
- Conserved source-index label: `Evaluation Provenance（评估溯源）` appears only as a fenced example under `Examples（示例）`; it is not a standalone H2 owner.

## Purpose（目的）

本规则定义中文知识库怎样同时满足可读性和技术精确性：

> 中文负责解释问题、机制、因果、比较、边界和结论；英文只在保持身份、行业语义或机器接口精确性时保留。

它禁止两种极端：把所有技术词机械翻译，导致名称、协议、参数或接口失真；用大量英文标题、表头和关键词代替中文解释，使正文事实上成为英文提纲。

本规则适用于 canonical knowledge、Overview / MOC、Roadmap、Checklist、Source Note、Research Synthesis、Case Study、管理页面、图表和 Interview Card 的中文部分。

## Ownership Boundary（职责边界）

| Owner | Owns | Does not own |
|---|---|---|
| 本规则 | 中文优先表达、英文保留边界、标题中文注释、表格语言、语言验收 | 术语是否值得建立独立页面 |
| [[kernel/10 Writing and Formatting/01 Naming Language and Prose\|Naming Language and Prose]] | 文件命名、标题层级、段落与列表 | 英文词是否应保留 |
| [[kernel/05 Terminology/03 Naming Context and Linking\|Naming Context and Linking]] | canonical term、aliases、首次链接和复用 | 当前句子和表格使用哪种叙述语言 |
| [[kernel/10 Writing and Formatting/02 Mathematics Tables and Code\|Mathematics Tables and Code]] | 表格、公式和代码的结构与渲染 | 表头和解释性单元格的语言 |
| [[profiles/agent-atlas/interview/04 System Deep Dive and Bilingual Policy\|System Deep Dive and Bilingual Policy]] | Interview Card 的中英文答案结构和语义一致性 | 普通知识正文的大段英文 |

一个问题只能有一个 canonical owner。其它规则通过 Wiki Link 引用本页，不能复制一份略有不同的语言政策。

### Standards Corpus Exemption（标准语料豁免）

生效的 Cambium standards corpus（kernel + selected profile）豁免“英文标题必须加中文注释”的要求，理由：控制面文件以稳定英文标题保证 heading anchor 稳定性与工具兼容。本豁免仅适用于标准语料，不适用于知识正文。

## File And Folder Names（文件与文件夹名称）

- 文件夹和文件名使用英语。
- 文件夹和文件名不添加中文翻译、中文注释或双语后缀。
- 使用英文正式名称或行业通用缩写；验收项见 Acceptance And Audit。
- 正确：`Agent Harness.md`；错误：`Agent Harness（代理执行外壳）.md`。
- 中文名称放在 `aliases` metadata 或正文首次出现后的中文括号中，不写入文件名。
- 文件名保持稳定；为了增加中文说明不得创建一份中文同义文件。

## Headings And Titles（标题）

页面内部的 reader-facing headings 可以使用中文，也可以保留英文；保留英文时必须使用 `English Title（中文注释）` 格式。允许：`## 失败模式`、`## Failure Modes（失败模式）`；不允许无注释的 `## Failure Modes`。

- 中文 heading 不要求重复附加英文。
- 中文注释说明标题语义，不要求逐词直译，但不能改变范围。
- 标准缩写或专有名称可以保留，例如 `## XGBoost（极端梯度提升）`。
- schema、API 或 method 名作为标题时保留原标识，并附用途说明，例如 `## TaskOutput（任务输出记录）`。
- Source Note 中的官方文章标题可在 source identity 字段原样保留；页面结构 heading 仍遵守本规则。
- Interview Card 的 English Answer 专区按 Interview Standard 执行；其上级结构 heading 仍应让中文读者可识别。
- 文件名不需要中文注释，且不得为了显示文件名而增加重复 H1。

### Stable Heading Migration（稳定标题迁移）

给已有英文 heading 增加中文注释会改变 heading anchor。执行前必须：

1. 盘点所有 incoming heading links；
2. 原子更新 heading 和引用；
3. 运行 missing / ambiguous / heading resolution 检查；
4. 记录 migration evidence。

无法在当前 batch 安全迁移时，可以暂时保留旧 heading，并在紧邻下一行添加 `中文注释：...`，同时登记 Required repair；不能静默破坏已有 heading links，也不能把临时兼容状态宣告为最终合规。

## Protected English Tokens（受保护英文标识）

以下内容默认保留英文原文：

| Category | Examples | Required Chinese support |
|---|---|---|
| 组织、产品和模型身份 | `Anthropic`、`Claude` | 当前段落说明其角色 |
| 协议、框架、库和算法正式名称 | `MCP`、`XGBoost` | 首次出现说明全称或用途 |
| 行业通用缩写 | `MSE`、`RAG` | 首次出现给出中文含义或链接 |
| 代码和机器接口 | `run_id`、`TaskOutput` | 邻近中文解释字段语义 |
| 命令、路径和配置值 | `git status`、`/api/health` | 邻近中文说明操作或状态 |
| 数学符号和正式记号 | $x$、$\theta$ | 首次出现解释符号 |
| 无稳定中文译名或翻译会产生歧义的术语 | `checkpoint`、`rollout` 等 | 首次出现给出中文语境解释 |

“受保护”表示不得为了中文化而改写身份或机器标识，不表示可以省略中文解释。受保护英文在首次有意义出现时统一写成 `English Term（中文解释）`，例如 `RAG（检索增强生成）`；中文只能放在括号内，不得反向写成 `检索增强生成（RAG）`。

以下内容不属于受保护英文：

- 普通说明性表头，例如 `Meaning`、`Failure`；
- 可以自然表达的因果和比较句；
- 为了显得专业而堆叠的英文名词；
- 已有稳定中文表达且不会损失语义的通用概念。

判断顺序：

```text
Machine-consumed identifier?
 -> preserve exact English
External identity or official name?
 -> preserve exact English
Stable Chinese term without semantic loss?
 -> use Chinese only when preserving English identity has no value
English identity is useful or required?
 -> use English（中文） on the first meaningful occurrence
No stable translation or translation is ambiguous?
 -> preserve English; explain it in Chinese
Otherwise
 -> write the explanation in Chinese
```

## Body Prose（正文）

- 知识正文默认使用中文语法和完整中文句子；英文术语可以嵌入中文句子，但不能让一段话退化成英文关键词列表。
- 原因、机制、假设、限制、失败、比较、建议和结论必须用中文讲清楚。
- 首次有意义出现的技术概念统一使用 `English Term（中文解释）`（不得反向），并按 Terminology Standard 建立 Wiki Link。
- 同一页面后续重复出现时，不机械重复双语注释；保持术语显示一致。
- 英文完整段落只允许出现在明确例外区域：短原文引用、English Interview Answer、代码、schema 或必须保持原文的接口契约。
- Source Note 对英文来源进行中文准确转述；不能通过复制英文原文代替 claim extraction。

## Tables（表格）

- 面向读者的表格表头默认中文；比较维度、解释、机制、限制和结论使用中文；禁止整张表由英文表头、英文短语和关键词堆叠组成。
- 专有名词、参数、字段、枚举、公式和正式算法名称保留英文。
- 参数表可以保留 `max_depth` 等参数名，但作用、交互和风险必须用中文说明。
- 英文专有名词单元格不要求逐项翻译；邻近列必须提供足够中文上下文。
- 单元格内容过长时按 Mathematics Tables and Code 拆成段落，不能借中英双语把表格无限加宽。

例外：

- 原始 schema / API field matrix；
- literal configuration、enum 或 protocol contract；
- Source identity metadata；
- Interview Card 的独立英文回答表；
- 必须逐字保持的标准或外部接口摘录。

即使属于例外，表格前后仍必须用中文说明它解决什么问题、字段如何使用以及不能推出什么结论。

## Diagrams Schemas And Code（图表结构与代码）

- Mermaid、流程图和框架图的 reader-facing labels 默认使用中文，或使用 `English（中文）`。
- 节点中的产品、协议、组件正式名称和机器字段保留英文。
- 图中不能因为中文注释而删除关键节点、分支、失败路径或顺序。
- schema、代码和伪代码中的 identifiers 原样保留；代码块外用中文解释输入、输出、状态变化和错误路径。
- 不在代码标识内部插入中文，也不翻译可执行命令。

## Source And Interview Exceptions（来源与面试例外）

### Source Notes（来源笔记）

- 文件名保留 organization / author 与英文来源主题。
- source title、author、URL、version 等 identity 字段保持原文。
- claims、limitations、non-claims、affected notes 和 promotion decision 使用中文。
- 必要短引文可保留原文，但必须有中文语义说明，且不能用大段引用替代分析。

### Interview Cards（面试卡片）

- 中文回答和英文回答按 Interview Standard 分区，不要求把英文回答逐句改成中文。
- 中文解释区、评分信号、误区和系统分析遵循本规则。
- 英文标题若不位于明确的 English Answer 区域，仍需中文注释。
- Interview 双语政策的 canonical owner 是 [[profiles/agent-atlas/interview/04 System Deep Dive and Bilingual Policy|11/04]]，本页不复制其规则。

## Terminology And Wiki Links（术语与链接）

- 文件名使用英文 canonical name；中文名写入 `aliases` metadata，并在正文中作为英文链接后的括号注释。
- 当前段落负责说明“为什么这里需要这个术语”；Term Note 负责完整定义。
- 第一次有意义出现时可以使用 `[[Data Leakage]]（数据泄漏）`：链接可见文本保留英文 canonical identity，中文解释放在链接后的全角括号内。
- 后续可以使用 `Data Leakage` 或在不会产生歧义的中文句子中使用“数据泄漏”，但不在每个表格和段落重复双语定义。
- 无稳定中文译名的术语可以保留英文链接，例如 `[[Agent Harness]]`，但首次出现必须给出中文角色说明。
- 不为中文名和英文名分别创建两份 canonical note。

## Acceptance And Audit（验收与审计）

语言验收属于 `content_and_depth` 的 acceptance predicate，不新增一个可以绕开内容正确性的独立完成状态。

单页关闭前至少确认：

- 文件名和文件夹名只有英文，无中文注释；
- reader-facing 英文 headings 有中文注释；
- 所有双语标题和首次术语注释都使用 `English（中文）`，不存在反向 `中文（English）`；
- 正文以中文完整解释为主；
- 表头和解释性单元格以中文为主；
- protected English tokens 没有被错误翻译；
- 普通英文说明没有被误当专有名词保留；
- 代码、schema、Source 和 Interview 例外边界明确；
- 中文翻译没有改变 claim、公式、范围或不确定性；
- 首次术语解释和 Wiki Link 可导航；
- 没有通过机械替换破坏 heading links、代码或 identifiers。

自动检查可以发现：

- 英文-only heading candidates；
- 英文-only reader-facing table headers；
- 中文字符进入文件名；
- 同一页面术语大小写或连字符漂移；
- language migration 后的 unresolved heading links。

字符比例和英文密度只能产生 review candidates，不能自动判错，因为代码、schema、Source identity 和 Interview English sections 可能合法。最终判断必须执行有范围、有例外记录的人工或模型审阅。

### Formatting Anti-patterns（格式反模式）

- Reader-facing 英文标题没有中文注释。
- 双语标题或术语写成 `中文（English）`，而不是规定的 `English（中文）`。
- 普通说明性表头和解释单元格几乎全是英文，导致中文正文退化成英文提纲。

## Migration And Invalidation（迁移与失效）

采用本语言合同不要求无差别立即重写全部历史页面。

既有内容迁移必须：

1. 先生成英文-only headings、英文-heavy tables 和英文解释段落的 inventory；
2. 排除代码、schema、Source identity、official title 和 English Interview Answer；
3. 按 domain、note type 和风险形成有界 repair batch；
4. 优先修复活动 batch、P0/P1 canonical owners、MOC/Roadmap 和高复用表格；
5. 翻译后复核语义，并运行 heading/link/table deterministic checks；
6. 只重跑被影响的 AuditReceipt 维度。

正常失效边界：

| Change | Normally invalidates |
|---|---|
| 只修改普通说明语言且语义不变 | `content_and_depth` 的语言 predicate |
| 修改 heading 或 Wiki Link alias | `structure_and_links`、`coverage_and_integration` |
| 翻译改变 claim 范围或不确定性 | `content_and_depth`、`source_and_currentness` |
| 翻译改变公式符号或数值语义 | `formula_and_numeric` |
| 修改 Interview Card 中英文回答 | `interview` |
| 修改表格宽度但无具体显示问题 | deterministic structure check；不自动触发视觉识别 |

active、paused 和 completion-candidate task 必须按 [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation#Active-task Adoption|Active-task Adoption]] 记录版本变化、重新解析本规则，并把受影响 acceptance predicate 纳入 AuditPlan。

## Examples（示例）

合规标题与首次术语：

```markdown
## Evaluation Provenance（评估溯源）
```

不合规的英文堆叠（正文退化为英文提纲）：

```markdown
Task output -> decision policy -> action -> outcome evidence.
```

改为：模型先产生 `TaskOutput`，Harness 再通过 decision policy 将其转换为候选动作；动作执行后的 authoritative outcome 才能进入结果证据链。

## Related（相关规则）

- [[kernel/10 Writing and Formatting Standard|Writing and Formatting Standard]]
- [[kernel/10 Writing and Formatting/01 Naming Language and Prose|Naming Language and Prose]]
- [[kernel/10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]]
- [[kernel/10 Writing and Formatting/04 Rendering and Formatting Review|Rendering and Formatting Review]]
- [[kernel/05 Terminology/03 Naming Context and Linking|Naming Context and Linking]]
- [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]]
- [[profiles/agent-atlas/interview/04 System Deep Dive and Bilingual Policy|System Deep Dive and Bilingual Policy]]
- [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]]
- [[Knowledge Base Standards/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|Audit Evidence Reuse and Invalidation]]
