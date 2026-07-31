## Navigation

- Parent: [[kernel/05 Terminology Standard|05 Terminology Standard]].
- Previous: [[kernel/05 Terminology/02 Ownership and Term Structure|Ownership and Term Structure]].
- Next: [[kernel/05 Terminology/04 Terminology Acceptance|Terminology Acceptance]].

## Naming And Aliases

- 文件名使用由所选 profile 的 `Language Contract` 登记的 canonical identity。
- 全称、缩写、同义词和多语言名称放入 `aliases`；具体语言取值由 `Language Contract` 登记。
- 不为缩写和全称分别创建两份文件。
- 同名但语义不同的术语通过领域路径消歧。
- 重命名 Term Note 前先检查 incoming links 和 aliases。

具体命名与 alias 示例由 `Language Contract` 的 `Terminology Naming And Aliases` 提供。

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

## Link Frequency

- 第一次有意义地出现术语时建立链接。
- 同一页面后续重复出现通常不反复链接。
- 链接不能代替当前段落必要的上下文。
- 不为了图谱密度链接普通词。
- 路径歧义时使用 path-qualified wiki link。
