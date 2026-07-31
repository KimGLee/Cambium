## Navigation

- Profile: [[profiles/agent-atlas/profile|Agent Atlas Profile]].
- Kernel contract: [[kernel/04 Content Depth Standard|04 Content Depth Standard]].

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
- 双语显示顺序只能是 `English Term（中文解释）`，不能写成
  `中文解释（English Term）`。
- aliases 可以同时保存英文全称、缩写和中文同义词，但 alias metadata 不改变正文显示顺序。
- 具体标题、正文、表格、图表、Source 和 Interview 例外由
  [[Knowledge Base Standards/10 Writing and Formatting/05 Chinese-first Technical Language|Chinese-first Technical Language]]
  统一维护。

## Terminology Kernel Binding

- Kernel owner: [[kernel/05 Terminology/03 Naming Context and Linking|Naming Context And Linking]]
