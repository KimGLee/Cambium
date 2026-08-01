## Navigation

- Parent: [[kernel/11 Expression Layer Standard|11 Expression Layer Standard]].
- Previous: [[kernel/11 Expression Layer/06 Sequence and Progress Semantics|Sequence and Progress Semantics]].

## Migration Policy

从既有位置迁移表达内容时，顺序必须为：

1. 识别 canonical knowledge owner、目标表达 owner 与旧内容之间的映射。
2. 先在目标 owner 创建完整内容。
3. 验证目标内容、证据绑定和 links 均可用。
4. 在原位置建立指向目标 owner 的可解析 wiki link。
5. 确认内容守恒后，才删除原位置的重复表达。
6. 验证没有内容丢失、重复 owner 或断链。

禁止先删除旧内容，再等待未来补建目标。拆分、重复与 owner 规则同时服从 [[kernel/03 Note Types and Ownership/03 Split and Duplication Policy|Split and Duplication Policy]]。

## Scoped Migration Audit

每个迁移 batch 扫描其 changed / owned scope；全局残留扫描只在注册的批次关闭 gate 中执行。Terminal verification 复用仍有效的 receipts，只重新深审 changed、invalidated、overdue 和抽样对象。

每个候选项必须归入以下一种 disposition：

| Disposition | Meaning |
|---|---|
| Migrate | 完整表达内容迁入已经建立的目标 owner |
| Minimal Context | 原位置只保留当前 canonical 段落可读所需的一句最小解释 |
| Owner Link | 原位置只保留指向目标表达 owner 的可解析 wiki link |
| Not Expression Content | 标题相似，但内容实际属于 canonical mechanism、evidence 或 evaluation owner |

## Candidate-only Automation

自动扫描只能发现 migration candidates，不能直接删除或改判内容。目标 owner 尚未完整建立并通过链接验证时，不得清空旧内容；扫描结果必须经过逐项 disposition。

同类自动检查的 candidate boundary 见 [[kernel/10 Writing and Formatting/04 Rendering and Formatting Review#Formatting Anti-patterns|Formatting Anti-patterns]]。

## Acceptance Criteria

- 目标表达 owner 在删除重复内容前已经存在并可解析。
- Canonical notes 不再维护由表达 owner 完整拥有的重复表达。
- Canonical owners 与表达产物之间的必要 links 双向、可解析且无歧义。
- 每个 migration candidate 都有明确 disposition；迁移后没有内容丢失、重复 owner 或断链。
- 定义、机制、指标和案例结论可以回溯到 canonical knowledge、evidence 与 evaluation provenance。
- `emerging`、`contested`、`unknown` 或其它证据限制在迁移后仍被保留。
- 自动扫描结果只作为候选证据，没有被当作自动删除授权或完成证明。
