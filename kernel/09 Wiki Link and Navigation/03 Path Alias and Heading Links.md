## Navigation

- Parent: [[kernel/09 Wiki Link and Navigation Standard|09 Wiki Link and Navigation Standard]].
- Previous: [[kernel/09 Wiki Link and Navigation/02 Structural and Bidirectional Links|Structural and Bidirectional Links]].
- Next: [[kernel/09 Wiki Link and Navigation/04 MOC Related and Link Creation|MOC Related and Link Creation]].

## Path And Alias Rules

- 同名文件存在歧义时必须使用完整 vault-relative path。
- 显示文本使用 alias，例如 `[[Knowledge Base Standards/00 Standards Overview|Standards Overview]]`。
- Markdown 表格中的 wiki alias pipe 必须转义：`\|`。
- 文件移动后必须更新显式 path links。
- 不创建只有 alias 不明确 target 的链接。
- Standards 领域级引用可以指向 stable MOC；引用具体规则、流程或 gate 时必须指向 folder 内的 canonical leaf module。
- Task Contract、Read Set 和 migration map 使用完整 vault-relative module path，不能只记录模糊的 Standard 编号。

## Heading Links

当引用的是一个具体结论或流程时，优先链接 heading：

```markdown
[[kernel/09 Wiki Link and Navigation/04 MOC Related and Link Creation#Link Creation Policy|Link Creation Policy]]
```

Heading 重命名会破坏这种链接，因此稳定的核心 heading 不应随意修改。

章节从 monolithic note 迁移到 leaf module 后，必须把 Vault 内旧 heading links 更新到新 owner；原 path-only link 可以继续指向 stable MOC。
