## Navigation

- Parent: [[Knowledge Base Standards/05 Terminology Standard|05 Terminology Standard]].
- Previous: [[Knowledge Base Standards/05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]].
- Next: [[Knowledge Base Standards/05 Terminology/04 Interview and Acceptance|Interview and Acceptance]].

## Naming And Aliases

- 文件名使用最常用的英文正式名称或行业通用缩写。
- 全称、缩写、同义词、中英文名放入 `aliases`。
- 不为缩写和全称分别创建两份文件。
- 同名但语义不同的术语通过领域路径消歧。
- 重命名 Term Note 前先检查 incoming links 和 aliases。

示例：

```yaml
type: term
domain: ai-systems
scope: shared
aliases:
  - Idempotent
  - 幂等性
```

## Contextual Use

不推荐：

```markdown
系统使用 [[Idempotency]]。
```

推荐：

```markdown
工具发生 timeout 后可能已经产生副作用，因此 retry 前必须通过
[[Idempotency]]（幂等机制）避免重复扣款或重复写入。
```

当前页面解释“为什么这里需要幂等”，Term Note 解释“幂等完整是什么”。

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

## Link Frequency

- 第一次有意义地出现术语时建立链接。
- 同一页面后续重复出现通常不反复链接。
- 链接不能代替当前段落必要的上下文。
- 不为了图谱密度链接普通词。
- 路径歧义时使用 path-qualified wiki link。
