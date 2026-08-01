## Navigation

- Profile manifest：[[profiles/agent-atlas/profile|Agent Atlas Profile]]。
- Kernel Read Set index：[[kernel/Read Sets/00 Read Sets Index|Read Sets Index]]。

## Compatibility Contract

- 本 provider 是仅对 `agent-atlas` 生效的 compatibility binding；其它 profile 不继承它。
- Artifacts 是只读、逐字节保留的 v2.3 snapshots。它们保留生产基线行为，但不是 canonical rule owner。
- 解析关系固定为 `stable Card ID -> legacy snapshot + canonical Read Set`；canonical Read Set 及其 leaf modules 始终是执行权威。
- 归档中的 `source_files` 与 `source_hash` 是历史编译 metadata，只描述 pre-split layout，不是当前 resolver inputs。
- Snapshot 与 canonical Read Set 冲突或不能覆盖当前情形时，执行必须升级回读 canonical source。

## Card Resolution Table

| Card ID | 只读 v2.3 snapshot | Canonical Read Set |
|---|---|---|
| `Card 00` | [[legacy/cards/00 Card Index\|Card Index]] | [[kernel/Read Sets/00 Read Sets Index\|Read Sets Index]] |
| `Card 01` | [[legacy/cards/01 Core Bootstrap Card\|Core Bootstrap Card]] | [[kernel/Read Sets/01 Core Bootstrap Read Set\|Core Bootstrap Read Set]] |
| `Card 02` | [[legacy/cards/02 Single Note Authoring Card\|Single Note Authoring Card]] | [[kernel/Read Sets/02 Single Note Authoring Read Set\|Single Note Authoring Read Set]] |
| `Card 03` | [[legacy/cards/03 Module Build Card\|Module Build Card]] | [[kernel/Read Sets/03 Module Build Read Set\|Module Build Read Set]] |
| `Card 04` | [[legacy/cards/04 Source-driven Expansion Card\|Source-driven Expansion Card]] | [[kernel/Read Sets/04 Source-driven Expansion Read Set\|Source-driven Expansion Read Set]] |
| `Card 05` | [[legacy/cards/05 Interview Content Card\|Interview Content Card]] | [[profiles/agent-atlas/interview/05 Interview Content Read Set\|Interview Content Read Set]] |
| `Card 06` | [[legacy/cards/06 Migration and Refactor Card\|Migration and Refactor Card]] | [[kernel/Read Sets/06 Migration and Refactor Read Set\|Migration and Refactor Read Set]] |
| `Card 07` | [[legacy/cards/07 Long-running Execution Card\|Long-running Execution Card]] | [[kernel/Read Sets/07 Long-running Execution Read Set\|Long-running Execution Read Set]] |
| `Card 08` | [[legacy/cards/08 Audit and Completion Card\|Audit and Completion Card]] | [[kernel/Read Sets/08 Audit and Completion Read Set\|Audit and Completion Read Set]] |
| `Card 09` | [[legacy/cards/09 Standards Governance Card\|Standards Governance Card]] | [[kernel/Read Sets/09 Standards Governance Read Set\|Standards Governance Read Set]] |
| `Card 10` | [[legacy/cards/10 Maintenance Run Card\|Maintenance Run Card]] | [[kernel/Read Sets/10 Maintenance Run Read Set\|Maintenance Run Read Set]] |

## Governance Write-back Precondition

当前 `Tools/stamp_cards.py` 只扫描 `Cards/*.md`，不能验证这个 legacy compatibility provider。零文件匹配或 zero-card scan 返回成功都不构成 synchronization pass，不得作为 governance evidence。

本次归档迁移明确为 no-recompile。任何后续影响 Runtime Cards 的 governance change，都必须保持未关闭，直到 active provider 或兼容 tool adapter 重生成或验证受影响 artifacts，并完成所需 write-back check。该 operational precondition 不放宽 governance gate。
