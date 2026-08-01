## Navigation

- Parent: [[kernel/00 Standards Overview|00 Standards Overview]].
- Previous: [[kernel/00 Standards Control/02 Task Routing and Pre-execution|Task Routing and Pre-execution]].
- Next: [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]].

## Standards Control

| Field | Value |
|---|---|
| Standards version | `{{ release_version }}` |
| Status | `{{ release_status }}` |
| Effective date | `{{ release_effective_date }}` |
| Change authority | User's explicit governance instruction |
| Content-task behavior | Frozen; read-only control plane |

Standards 生命周期为：

```text
draft
 -> approved
 -> superseded
```

修改规则时必须：

1. 明确这是 governance change，而不是普通内容编辑。
2. 记录受影响 Standards 和原因。
3. 提升 `standards_version`。
4. 更新 `00` 的 routing 和 change summary。
5. 按修订记录的 changed-predicate 清单执行 [[kernel/12 Quality Assurance/07 Audit Evidence Reuse and Invalidation|12/07]] 的 Active-task Adoption；清单为空即 no-op，一行 adoption receipt 即完成。

用户批准 Standards 不等于批准对全部旧页面立即批量迁移 Frontmatter。迁移范围仍需进入具体 task contract。

## Revision Write-back Checklist

任何 Standards 修订在关闭前，必须核对并同步以下快照位置；修订未完成回写不得关闭。无 predicate 变化的修订走 no-op 轻量路径：仅核对实际被改文件涉及的位置，字节 diff＋一行 adoption receipt 即完成：

- [[kernel/00 Standards Control/04 Control State and Scope|Control State and Scope]] 的状态表。
- [[kernel/00 Standards Overview|00 Standards Overview]] 的 Protected Defaults 与 Task Router。
- 相关 domain MOC 的 Module Index。
- 相关 Read Set 的 target 列表。
- [[kernel/00 Standards Control/05 Core Principles and Standards Map#Cross-domain Rule Registry|Cross-domain Rule Registry]]。
- 通过所选 profile 注册的 `Runtime Card Provider` 重新生成受影响的 Runtime Cards；这些 artifacts（包括 provider 解析的 index artifact）均为编译产物，禁止手改。受影响 = `source_files` 含被改文件的卡。用 `Tools/stamp_cards.py` 盖戳（`--set-version` 同步 provider 解析的 index artifact 版本戳）；修订关闭前必须运行 `Tools/stamp_cards.py --check` 并通过。
- 重新生成 `Tools/vocab.yaml`（编译产物，词表 owner 为各标准原文）。

执行端为 gate 或审计自建的持久工具，必须经轻量 governance 登记纳入 Tools/ 管理并指定 owner；存量自建工具在下一次 governance 时补登记，登记前其输出仅作参考、不作为 gate 唯一证据。

## Control Accretion Rule

任何新增检查、冻结、失效或对账义务的修订，Amendment 必须回答三问：

1. 该风险现有哪一层负责？为何不足？
2. 新义务的 canonical gate 归属哪一层？（不得多层并存）
3. 被替代的旧层是否删除？不删除的理由？

三问不全，修订不得通过。控制义务与内容规则一样纳入 Registry 管理。

## Leaf Module Size Budget

- Leaf module 目标 ≤5KB，软上限 6KB。
- 超限时优先削减示例；仍超限再考虑拆分，拆分走本页 governance change 流程。
- MOC 与 Read Set 不设此限，但同样从简。
- 示例每个规则点默认 good / bad 各一。
- 每个获批例外必须登记对象、测量值、必要性、增长上限与后续处置；未经新的 governance change，不得超过登记上限。

| Exception register | Active entries |
|---|---|
| Leaf module exceptions | None; register is open for an authorized governance change |
| Control-plane exceptions | None; register is open for an authorized governance change |

## Execution-Acceptance Ownership Convention

- `02 Build Execution` 域持有执行原则与触发时点；`12 Quality Assurance` 域持有验收清单。
- 同一事项两侧不得各自全文持有；执行侧通过 Wiki Link 引用验收侧的细目，不复制清单内容。

## Change Summary

Active release register：empty until the first governance change。每次登记必须填写 version、date、change、changed-predicate 清单与 Active-task Adoption 要求；清单为空时记录 no-op adoption receipt。

| Version | Date | Change | Changed predicates | Adoption requirement |
|---|---|---|---|---|
