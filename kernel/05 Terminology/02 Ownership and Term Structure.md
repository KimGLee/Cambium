## Navigation

- Parent: [[kernel/05 Terminology Standard|05 Terminology Standard]].
- Previous: [[kernel/05 Terminology/01 Terminology Extraction|Terminology Extraction]].
- Next: [[kernel/05 Terminology/03 Naming Context and Linking|Naming Context and Linking]].

## Ownership

术语使用“最低合理归属”规则：

1. 有明确领域归属：放在该领域。
2. 多领域复用且有基础学科归属：放在所选 profile 注册的 `Shared Foundation Layer`。
3. 生产系统通用：放在所选 profile 注册的 `Production Systems Layer`。
4. 真正跨领域且无自然 owner：放在所选 profile 注册的 `Cross-domain Concepts Layer`。
5. 表达层不改变术语 owner，`Expression Layer Artifact` 只引用它。

不建议建立一个无分类、无限增长的全局 Glossary 文件夹。

## Suggested Structure

具体目录树由所选 profile 的 `Profile Scope` 在 `Terminology Structure` 中登记。

该结构需要在整体架构确认后再创建，当前规则不自动移动现有术语页。

## Term Note Structure

一个完整 Term Note 通常包含：

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

涉及数学时增加公式；涉及系统时增加输入输出和生命周期；涉及协议时增加角色、边界和版本信息。
