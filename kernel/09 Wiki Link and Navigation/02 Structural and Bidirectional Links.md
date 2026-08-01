## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/09 Wiki Link and Navigation/01 Link Semantics and Body Links|Link Semantics and Body Links]].
- Next: [[kernel/09 Wiki Link and Navigation/03 Path Alias and Heading Links|Path Alias and Heading Links]].

## Structural Links

核心笔记至少应能导航到：

- 一个 Parent / Overview。
- 必要 Prerequisites。
- 关键 Components 或子概念。
- 至少一个 Application、Alternative 或 Failure link。
- 适用时链接至少一个由 `Expression Layer Entry` 注册的 `Expression Layer Artifact`。

Source Note 还应链接受影响的 knowledge notes；Research Synthesis 应链接 source set、现有 owners 和建议改变的 graph nodes。Canonical note 不要求列出所有 Source Notes，但关键时效性 claim 必须保留可追溯 evidence link。

不能机械要求固定链接数量，关系真实性优先。

## Bidirectional Knowledge Flow

推荐关系：

```text
Overview -> Topic
Topic -> Prerequisite / Component / Alternative
Source Note -> Affected Knowledge Notes
Research Synthesis -> Source Notes + Canonical Topics
Canonical Topic -> Key Evidence / Research Synthesis
Case Study -> Canonical Topic
Canonical Note <-> Expression Layer Artifact
Cheat Sheet -> Canonical Note
```

所选 knowledge host 的 backlinks capability 可以提供反向发现，但关键导航仍应在正文中显式存在。
