## Navigation

- Parent: [[Knowledge Base Standards/12 Quality Assurance Standard|12 Quality Assurance Standard]].
- Previous: [[Knowledge Base Standards/12 Quality Assurance/01 Quality Dimensions and Single Note Review|Quality Dimensions and Single Note Review]].
- Next: [[Knowledge Base Standards/12 Quality Assurance/03 Module Coverage and Batch Review|Module Coverage and Batch Review]].

## Rendering Verification Levels

渲染验收采用 `deterministic-first, visual-by-exception`：先用可重复、可全量运行的确定性方法判断源文件和静态构造；只有这些证据无法消除最终显示的不确定性时，才升级到 UI、截图或视觉识别。

本标准中的“视觉识别”包括：

- 打开 Obsidian 或其它 host UI 后人工观察页面。
- 根据截图判断布局、遮挡、溢出、颜色或可读性。
- 使用 OCR、视觉模型或屏幕识别代替直接解析源文件。

新增或修改 diagram、table、formula、image、callout 或 embed 本身不构成视觉升级理由。它们默认触发对应的 Level 0 / Level 1 验证。

### Level 0: Source And Structural Validation

所有变更页面都必须执行：

- Markdown heading、fence、link 和 table pipe 检查。
- 公式 delimiter、图片路径、embed path 和 Mermaid fence 检查。
- 直接提取正文，检查结构、重复、缺失章节和术语链接。

纯文本页面在没有可渲染构造时通常止于本级。Level 0 是内容和结构检查的主路径，必须全量覆盖，不能用 UI 浏览代替。

### Level 1: Static Render Or Compile

出现以下内容时执行对应静态验证：

- Mermaid diagram：使用 Mermaid compiler。
- 数学公式：使用支持当前 Markdown / Math 语法的渲染器或可重复的 preview。
- Markdown table：检查实际列数、escaped wiki alias 和长单元格。
- SVG、图片和 assets：检查文件存在、尺寸、引用路径和可解析性。

Level 1 必须优先使用 compiler、parser、structured extraction、文件探测和可重复的非交互 preview。生成静态 artifact 不等于授权视觉判断；只要编译结果、结构数据和几何信息已经能回答验收问题，就不继续打开 UI 或截图。

Level 1 通过不代表任意 Obsidian 主题、插件或 CSS 下一定正常，但这种理论可能性不能单独触发 UI 检查。

### Level 2: Targeted Visual Recognition Exception

只有满足以下至少一个客观条件时，才允许进行最小范围视觉识别：

1. Level 0 / Level 1 结果互相冲突，或者通过后仍无法回答一个具体的最终显示问题。
2. 用户报告可复现的视觉缺陷，而源文件、compiler 或静态 artifact 无法解释或确认该缺陷。
3. Obsidian theme、CSS snippet、插件、字体或 host rendering contract 发生变化，且影响无法由配置和静态验证确定。
4. 确定性检查发现疑似 overflow、occlusion、clipping、layering 或 viewport-dependent layout，但无法判定最终 host 行为。
5. 用户明确要求对一个指定页面、区域、主题或 viewport 做视觉验收。

执行 Level 2 时必须：

- 先记录仍未解决的具体问题和触发条件。
- 只打开能回答该问题的最小代表页面、区域和 viewport。
- 需要留证时只截取目标区域；不得用广泛录屏或全库浏览代替定位。
- 记录 target、expected、observed、result 和不确定性是否已消除。

若没有上述触发条件，不存在 UI、截图或视觉模型证据不构成 QA 缺口。

### Level 3: Expanded Or Full UI Review

只有以下情况需要扩大到模块或全库：

- Level 2 已确认可重复、可能影响同类页面的系统性问题。
- 修改了全局 CSS、主题、插件、字体或 asset policy。
- 大规模迁移改变了 host rendering contract、asset loading 或 embed behavior，且确定性验证不足以覆盖。
- 用户明确要求完整视觉验收。

Level 3 必须定义有界 sample matrix，包括受影响模式、代表页面、viewport 和停止条件。不能因为已经打开 UI 就无边界扩展检查。

### Level 4: Temporal Recording Exception

录屏只用于静态证据无法表达的时间相关或交互问题，例如：

- scroll、hover、focus、animation 或 responsive transition。
- 插件加载、异步 asset、状态切换或短暂闪烁。
- 必须观察动作前后顺序才能复现的 host-specific failure。

静态 Markdown、表格、公式、普通图片、链接、正文完整性和单帧布局不允许默认使用录屏验证。Level 4 必须记录为什么 source、static artifact 和 targeted screenshot 都不足，并只录制复现问题所需的最短动作序列。

### Escalation Record

每个 batch 或 audit 使用以下枚举记录最高实际级别：

```text
rendering_mode:
  source-only
  deterministic-static
  targeted-visual-exception
  expanded-ui
  temporal-recording

visual_trigger:
unresolved_question:
target:
result:
```

当 `rendering_mode` 为 `source-only` 或 `deterministic-static` 时，`visual_trigger` 写 `not_applicable`。Level 2–4 缺少客观 trigger 或 unresolved question 时不能执行。

UI、截图和录屏只能回答显示或交互问题，不能证明正文正确、来源可靠、Wiki links 可解析、公式语义正确、coverage 完整或 Completion Gate 已通过。
