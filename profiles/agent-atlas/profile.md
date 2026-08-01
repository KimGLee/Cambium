## Profile Identity

- `profile_id`: `agent-atlas`

## Implemented Slots

- `Profile Scope`: [[profiles/agent-atlas/scope-and-architecture|Scope And Architecture]]
- `Priority Rubric`: [[profiles/agent-atlas/priority-rubric|Priority Rubric]]
- `Vocabulary Extensions`: [Vocabulary Extensions](vocabulary-extensions.yaml)
- `Language Contract`: [[profiles/agent-atlas/language-contract|Language Contract]]
- `Expression Layer Entry`: [[profiles/agent-atlas/expression-layer|Expression Layer]]
- `Source Policy`: [[profiles/agent-atlas/source-policy|Source Policy]]
- `Role Registry`: [[profiles/agent-atlas/registries/roles|Role Registry]]
- `Audit Dimension Registry`: [[profiles/agent-atlas/registries/audit-dimensions|Audit Dimension Registry]]
- `Registered Scan Registry`: [[profiles/agent-atlas/registries/registered-scans|Registered Scan Registry]]
- `Routing And Gate Registry`: [[profiles/agent-atlas/registries/routing-and-gates|Routing And Gate Registry]]
- `Runtime Card Provider`: [[profiles/agent-atlas/card-compatibility|Card Compatibility Provider]]

## Registered Extensions

- `Expression Layer Artifact`: [[profiles/agent-atlas/interview/01 Interview Architecture and Separation#Interview Card|Interview Card]]
- `Expression Status Axis`: [[profiles/agent-atlas/interview/02 Card Granularity Coverage and Categories#Interview Coverage Status|Interview Coverage Status]]

## Runtime Card Provider Binding

- Mode: `legacy-v2.3-snapshot-compatibility`。
- Scope: `agent-atlas-only`；其它 profile 不继承本 binding。
- Artifact root: `legacy/cards/`（read-only、byte-verbatim v2.3 snapshots）。
- Index: 使用 `Implemented Slots` 中的 `Runtime Card Provider` binding，按 stable Card ID 解析 snapshot 与 canonical Read Set。
- Canonical authority: 对应 kernel Read Sets 与 leaf modules；artifact 冲突时升级回读原文。
- Historical metadata: archived `source_files` 与 `source_hash` 只描述 pre-split compilation，不作为当前路径或 freshness 证明。
- Write-back precondition: 当前 `Tools/stamp_cards.py` 仅扫描 `Cards/*.md`，不支持此 legacy provider；zero-match 不构成 pass。未来 governance task 在 active provider 或兼容 tool adapter 完成实际同步检查前不得关闭。

## Execution Default Overrides

| Kernel 默认项 | Profile 选择 | 生效值 |
|---|---|---:|
| `concurrency_cap` | `use-kernel-default` | `3` |
| `batch_size.S` | `use-kernel-default` | `24` |
| `batch_size.M` | `use-kernel-default` | `10` |
| `batch_size.L` | `use-kernel-default` | `6` |
| `priority_quota.P0` | `use-kernel-default` | `15%` |
| `priority_quota.P1` | `use-kernel-default` | `35%` |
| `maintenance.unselected_rounds_before_log_only` | `use-kernel-default` | `3` |
| `maintenance.incoming_retarget_divisor` | `use-kernel-default` | `6` |

未登记其它值即表示本 profile 不覆写这些 kernel defaults；task contract 仍可在 kernel 允许的范围内显式覆写。

## Task Contract Defaults

- Logical center：`Agent/Harness`。
- Expression artifact：双语 `Interview Card`。
- Directory and scope decisions：使用 `Profile Scope` 已登记的结构与范围。
- Display language：使用 `Language Contract`。
- Expression routing：使用 `Expression Layer Entry` 与 `Routing And Gate Registry`。

任务没有显式改变这些 profile defaults 时，不重复请求批准；kernel 的 ownership、source-to-knowledge、quality 和 safety 不变量继续生效。
