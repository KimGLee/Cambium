## Navigation

- Parent: [[kernel/10 Writing and Formatting Standard|10 Writing and Formatting Standard]].
- Previous: [[kernel/10 Writing and Formatting/02 Mathematics Tables and Code|Mathematics Tables and Code]].
- Next: [[kernel/10 Writing and Formatting/04 Rendering and Formatting Review|Rendering and Formatting Review]].

## Diagrams

图只在能显著降低理解成本时加入：

- Architecture diagram：组件和依赖。
- Sequence diagram：调用顺序和状态变化。
- Data flow：数据如何转换。
- Function plot：激活函数、loss 或分布。
- Decision table / tree：方案选择。

使用 Mermaid、可靠 SVG 或必要的生成图片。图后必须有正文解释，不能让图独自承担所有知识。

### Direction And Completeness

图的方向由知识结构决定，不使用统一的上下长条模板：

- 长的有序执行链、pipeline 和跨组件 handoff 优先考虑横向 `LR`。
- 层级、依赖树、状态分解和 ownership map 优先考虑纵向 `TD`。
- 多主体交互优先考虑 sequence diagram 或明确 swimlane。
- 循环、回退和恢复必须画出 back edge 或单独的 failure path。

图的第一目标是内容完整和顺序正确，其次才是单屏视觉紧凑。不得为了避免横向滚动而删除关键步骤、分支、状态、权限检查、effect receipt 或 recovery path。

当一个图过于复杂时，按知识责任拆成：

```text
Overview Architecture
 -> Detailed Execution / Sequence
 -> Failure And Recovery Flow
```

拆图后每张图都必须有明确入口、出口和与其它图的承接说明。横向滚动可以接受；语义缺失不可以接受。

### Diagram Semantics

- 节点名称描述真实对象、状态或动作，不使用含义模糊的 `Process`、`Handle`、`Do Work`。
- Reader-facing label 的语言、identity 保留值和显示顺序由所选 profile 的 `Language Contract` 定义；本页只保留 diagram semantics 和结构完整性。
- 边表示明确的调用、数据、控制、状态 transition 或 authority transfer；需要时使用 label。
- proposer output、gatekeeper validation / authorization 和 external execution 使用不同节点或 lane。
- Happy path、retry、timeout、cancel、unknown outcome 和 terminal verification 不应混成同一条无条件边。
- 图中的顺序、方向和正文描述必须一致。

## Assets

- 图片放在所属模块的 `Assets` 文件夹。
- 图片文件名使用由所选 profile 的 `Language Contract` 注册的 canonical identity，并表达内容。
- 不使用纯装饰图片。
- 所有图片先验证路径、格式、尺寸和引用；新增或修改 diagram、image 或 embed 时按 [[Knowledge Base Standards/12 Quality Assurance/02 Rendering Verification#Rendering Verification Levels|Rendering Verification Levels]] 执行 Level 0 / Level 1。
- 修改图后先用 compiler、结构提取和尺寸数据验证节点、边、label、顺序和完整性。只有确定性证据无法判断具体的可读性、overflow、occlusion 或 host-specific display 时，才升级到最小范围 visual exception。
- 内容明确依赖特定 desktop 或 mobile viewport 且存在未决布局问题时，才检查对应 viewport；不能因为存在多个 viewport 就默认逐一操作 UI。
