## Navigation

- Parent: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Previous: [[kernel/10 Writing and Formatting/03 Diagrams and Assets|Diagrams and Assets]].
- Next profile slot: `Language Contract`.

## Rendering Workflow

内容和结构检查以直接提取 Markdown 为主，渲染检查遵循确定性优先、视觉识别例外；渲染分级的 canonical 定义与升级条件见 [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification|12/02]]。

执行侧要点：纯文本编辑不默认需要打开所选 knowledge host 的 UI。新增 diagram、table、formula、image、callout 或 embed 也不自动触发 UI；先执行相应 compiler、parser、path、dimension 和结构验证。

只有 [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification#Level 2: Targeted Visual Recognition Exception|Level 2]] 的客观条件成立时，才打开最小页面或查看目标截图。录屏只适用于静态证据无法表达的时序或交互问题。Reading View 通过只表示被检查目标的显示正常，不表示内容、来源、链接和 Completion Gate 已经通过。

## Formatting Anti-patterns

- 重复标题。
- 日期出现在普通概念标题中。
- 只有 bullet list，没有解释段落。
- 公式符号未定义。
- Markdown table 因 wiki pipe 破裂。
- 过长表格代替完整章节。
- 图片与正文没有解释关系。
- 所有流程图都强制使用同一方向。
- 为了适配单个视口而删掉关键流程或失败路径。
- 把新增视觉构造本身当作 UI 抽样理由，而不先执行确定性验证。
- 每轮都重复打开页面、截图或录屏，却没有记录尚未解决的显示问题。
- 使用视觉识别读取本可直接解析的正文、链接、表格结构或配置。
- 使用大量粗体和装饰符号制造虚假层次。
以上 reader-facing language 反模式的 canonical 定义与例外边界由所选 profile 的 `Language Contract` 提供。

### Automated Language Review Boundary

字符比例、token pattern、heading 或 table-header density 等自动检查只能产生 review candidates，不能绕过 `Language Contract` 的 scoped exceptions 或直接判定内容失败；最终结论必须来自有范围的审阅。

### Formatting Migration Invalidation

格式或语言迁移只失效直接受影响的 audit dimensions：heading / link 变化至少失效 structure and links，语义、source、formula 或 `Expression Layer Artifact` 变化分别失效对应维度。所选 profile 的 `Language Contract` 提供具体映射和例外；active task 必须重新采用变更后的合同，不能无差别重跑无关 receipts。

## Related

- [[kernel/04 Content Depth Standard|Content Depth Standard]]
- [[kernel/09 Wiki Link and Navigation Standard|Wiki Link and Navigation Standard]]
- [[Knowledge Base Standards/12 Quality Assurance Standard|Quality Assurance Standard]]
- [[kernel/06 Knowledge Intake and Evolution Standard|Knowledge Intake and Evolution Standard]]
- 所选 profile 的 `Language Contract`
