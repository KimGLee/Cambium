## Navigation

- Parent: [[kernel/05 Terminology Standard|05 Terminology Standard]].
- Previous: [[kernel/05 Terminology/01 Terminology Extraction|Terminology Extraction]].
- Next: [[kernel/05 Terminology/03 Naming Context and Linking|Naming Context and Linking]].

## Ownership

Terminology uses the "lowest reasonable ownership" rule:

1. Clear domain ownership: place it in that domain.
2. Reused across multiple domains with a foundation-discipline home: place it in the `Shared Foundation Layer` registered by the selected profile.
3. Generic to production systems: place it in the `Production Systems Layer` registered by the selected profile.
4. Truly cross-domain with no natural owner: place it in the `Cross-domain Concepts Layer` registered by the selected profile.
5. The expression layer does not change a term's owner; the `Expression Layer Artifact` only references it.

Creating an uncategorized, unboundedly growing global Glossary folder is not recommended.

## Suggested Structure

The concrete directory tree is registered by the selected profile's `Profile Scope` under `Terminology Structure`.

This structure is to be created only after the overall architecture is confirmed; the current rule does not automatically move existing term pages.

## Term Note Structure

A complete Term Note usually contains:

```text
Full Name And Aliases（全称与别名）
Definition（定义）
Why This Term Exists（术语存在的原因）
Intuition（直觉理解）
Formal Meaning（形式化含义）
Notation / Data Structure（记号 / 数据结构）
Minimal Example（最小示例）
Where It Is Used（使用场景）
What It Is Not（它不是什么）
Common Misconceptions（常见误解）
Expression Layer Link（表达层链接）
Related Terms（相关术语）
Sources（来源）
```

When mathematics is involved, add formulas; when systems are involved, add inputs, outputs, and lifecycle; when protocols are involved, add roles, boundaries, and version information.
