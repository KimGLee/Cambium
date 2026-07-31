# Removed Instance Log

本日志只记录从 active `kernel + selected profile` 语料删除的部署痕迹。进入 legacy 的内容仍标记为 `removed-from-active`；空白 profile slot 或 role substitution 不恢复原实例内容。

| Log ID | Map row ID | Segment | Source file | Source heading | Source span SHA-256 | Action | Active result | Legacy target | Legacy span SHA-256 | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| `RI-0001` | `SM-0132` | `whole` | `01 Scope and Architecture/01 Scope Boundaries.md` | `Excluded Scope` | `cdf9328d4dc3d2b99766f199b5186b958c82a0e4a75c27536450a24e3a7bd4e3` | 删除具体排除块；profile 只初始化空白 exclusion slot | `removed-from-active` | — | — | 具体文件夹及其维护边界属于部署实例 |
| `RI-0002` | `SM-0135` | `existing-directory-modeling-fundamentals` | `01 Scope and Architecture/03 Foundation Preservation.md` | `Foundation Preservation Rule` | `c9ea89c096bc46696512c959216b87be1b09c7ce21622e73b80efbed62ab5f9d` | 删除现有目录断言，保留后续基础层扩展承诺 | `removed-from-active` | — | — | `Modeling Fundamentals` 是现有部署目录指涉 |
| `RI-0003` | `SM-0135` | `existing-directory-safety-permission` | `01 Scope and Architecture/03 Foundation Preservation.md` | `Foundation Preservation Rule` | `13401984158c6b5023515d6ac930d6479a92681e49de1a0ad3c99394e48a6aec` | 将具名现有 owner 替换为 profile 注册的安全内容 owner | `removed-from-active` | — | — | `Agent Knowledge/Safety Permission` 是现有部署路径与 owner 指涉 |
