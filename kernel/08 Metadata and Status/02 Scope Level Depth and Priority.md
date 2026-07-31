## Navigation

- Parent: [[kernel/08 Metadata and Status Standard|08 Metadata and Status Standard]].
- Previous: [[kernel/08 Metadata and Status/01 Frontmatter and Core Vocabularies|Frontmatter and Core Vocabularies]].
- Next: [[kernel/08 Metadata and Status/03 Status Axes|Status Axes]].

## Scope

- `shared`：多个顶层领域复用。
- `domain-specific`：主要属于一个领域。
- `case-specific`：只属于一个案例。
- `source-specific`：只描述一个外部来源。

所选 profile 可以通过 `Vocabulary Extensions` 追加 scope 值，但不能重定义上述基础值。

## Level

- `basic`：阅读当前范围其它核心内容前必须掌握。
- `intermediate`：需要基础知识，属于目标范围的核心能力。
- `advanced`：深入实现、理论边界或生产规模问题。

Level 代表前置难度，不代表内容 priority。

## Depth

- `atomic`
- `core`
- `system`

定义见 [[kernel/04 Content Depth Standard|Content Depth Standard]]。

## Priority

- `P0`：所选 profile 声明为必须掌握；缺失会阻断依赖内容或已声明目标。
- `P1`：所选 profile 声明为高优先级扩展；应达到该 profile 规定的 readiness predicate。
- `P2`：补充广度，可以在核心体系完成后建设。

P0 / P1 / P2 是固定三级轴，进入页面 tier 派生与配额挂钩机制；所选 profile 不得替换、增删或重定义该轴。P0 / P1 的具体授予条件由 `Priority Rubric` 注册。
