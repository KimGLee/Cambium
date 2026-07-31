## Navigation

- Parent: [[Knowledge Base Standards/03 Note Types and Ownership Standard|03 Note Types and Ownership Standard]].
- Previous: [[Knowledge Base Standards/03 Note Types and Ownership/01 Note Type Catalog|Note Type Catalog]].
- Next: [[Knowledge Base Standards/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]].

## Ownership Rules

每个知识对象必须有唯一 owner：

- Term Note owns the definition。
- Concept Note owns the mechanism。
- Process / Flow Note owns transition、branch、loop、state/effect change 和 termination semantics。
- Algorithm Note owns the algorithm behavior。
- Metric Note owns the metric interpretation。
- System Component Note owns the component contract。
- System Design Note owns component interaction。
- Source Note owns faithful representation of one source。
- Research Synthesis Note owns cross-source comparison and unresolved research state。
- Case Study owns application decisions。
- Interview Card owns interview expression。
- Overview / MOC owns module boundary and navigation。
- Roadmap owns learning order。

## Canonical Note Rules

- 一个概念只有一个 canonical note。
- 缩写、全称、中英文名称通过 aliases 和 wiki link alias 解决。
- 其它页面可以解释当前上下文中的作用，但不能复制完整通用定义。
- Process / Flow Note 可以引用组件 contract，但不能复制每个组件的完整实现；组件页也不能各自声称拥有同一端到端流程。
- canonical note 移动时必须更新所有 path-qualified links。
- 同名但语义不同的概念使用领域路径消歧，例如 RL State 与 Agent State。
- Source Note 和 Research Synthesis 不因为引用了概念而获得该概念的 canonical ownership。
- Interview Card、Roadmap、Cheat Sheet 或 Overview 中存在链接，不表示被链接的 canonical note 已经通过内容审阅。
