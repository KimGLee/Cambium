# Kernel / Profile Structure Proposal

## Status And Decision Boundary

本文件是 Cambium 第一期中文语料结构拆分的候选施工合同。它只定义目标结构、映射规则、批次顺序和验收不变量；在本文件提交并得到用户确认前，不移动或改写任何现有标准正文。

权威输入为 `docs/split_map.tsv`，行为回归基准为 `docs/golden_scenarios.md`。本方案只读取 Cambium 仓库，不依赖或访问任何外部知识库目录。

## Evidence Snapshot

`split_map.tsv` 含 404 个数据行、404 个唯一 `file + heading` key，覆盖 127 个源文件。所有已映射文件和标题均存在。

| Tag | Rows | Proposed treatment |
|---|---:|---|
| `kernel` | 218 | 默认迁入领域无关内核；执行 note 明示的 role substitution、instance segment 删除或 `examples` 中性化，规则本体不改写 |
| `mixed` | 92 | 按 note 做句子级 kernel / profile 拆分，必要时另含 instance deletion；生效两侧合读保持原语义 |
| `profile` | 32 | 默认整块迁入 `profiles/agent-atlas/`；note 明示的通用机制可上浮 kernel |
| `instance` | 10 | 从生效语料删除并逐行登记；仅迁移史类可在 legacy 保留追溯副本 |
| `nav` | 40 | 随该行所属的新语义宿主迁移 |
| `derived` | 11 | Cards 字节级归档至 `legacy/cards/`，本期不重编 |
| `profile-derived` | 1 | kernel base 与 selected profile extensions 分别持有 canonical 输入，生成物保留工具消费位置并重新编译 |
| **Total** | **404** | 每行在阶段 4 必须有明确去处 |

按原来源域统计：

| Source domain | Total | Kernel | Mixed | Profile | Instance | Nav | Derived | Profile-derived |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 00 | 41 | 14 | 20 | 0 | 4 | 3 | 0 | 0 |
| 01 | 15 | 7 | 4 | 1 | 1 | 2 | 0 | 0 |
| 02 | 28 | 18 | 8 | 0 | 0 | 2 | 0 | 0 |
| 03 | 19 | 15 | 1 | 0 | 1 | 2 | 0 | 0 |
| 04 | 20 | 16 | 2 | 0 | 0 | 2 | 0 | 0 |
| 05 | 21 | 13 | 3 | 2 | 1 | 2 | 0 | 0 |
| 06 | 18 | 16 | 0 | 0 | 0 | 2 | 0 | 0 |
| 07 | 22 | 18 | 2 | 0 | 0 | 2 | 0 | 0 |
| 08 | 23 | 13 | 8 | 0 | 0 | 2 | 0 | 0 |
| 09 | 18 | 12 | 4 | 0 | 0 | 2 | 0 | 0 |
| 10 | 33 | 9 | 7 | 13 | 1 | 3 | 0 | 0 |
| 11 | 22 | 0 | 10 | 10 | 0 | 2 | 0 | 0 |
| 12 | 38 | 19 | 14 | 1 | 1 | 3 | 0 | 0 |
| Read Sets | 55 | 31 | 9 | 4 | 0 | 11 | 0 | 0 |
| Tools | 20 | 17 | 0 | 1 | 1 | 0 | 0 | 1 |
| Cards | 11 | 0 | 0 | 0 | 0 | 0 | 11 | 0 |

## Architecture Contract

生效标准由两个显式输入合成：

```text
effective standard = kernel + one selected profile
```

- `kernel/` 只持有领域无关的过程、状态、所有权、证据、质量与完成语义。
- `profiles/<profile>/` 持有一个部署的 scope、优先级授予标准、语言合同、表达层、词表取值和扩展注册项。
- kernel 只按 profile role / slot 引用，不出现 `agent-atlas`、Agent/Harness、Interview 或具体厂商等实例名称。
- 一个规则单元只有一个 canonical owner；另一侧需要该规则时只做角色引用。
- `Tools/` 是执行工具面，不是 kernel 规则源；`legacy/` 默认不参与生效规则判定。第一期为保持 Card-first 路由，`profiles/agent-atlas/card-compatibility.md` 可将稳定 Card ID 解析到 `legacy/cards/` 的只读 v2.3 快照；这是唯一拟议的 legacy 运行兼容例外，Cards 仍不是 canonical source。
- `docs/` 保存迁移施工图、判定基线、删除登记、blockers 与最终守恒报告，不属于标准正文。

## Proposed Directory Tree

```text
Cambium/
├── README.md
├── kernel/
│   ├── 00 Standards Overview.md
│   ├── 00 Standards Control/
│   ├── 01 Scope and Architecture Standard.md
│   ├── 01 Scope and Architecture/
│   ├── 02 Knowledge Base Build Execution Standard.md
│   ├── 02 Build Execution/
│   ├── 03 Note Types and Ownership Standard.md
│   ├── 03 Note Types and Ownership/
│   ├── 04 Content Depth Standard.md
│   ├── 04 Content Depth/
│   ├── 05 Terminology Standard.md
│   ├── 05 Terminology/
│   ├── 06 Knowledge Intake and Evolution Standard.md
│   ├── 06 Knowledge Intake and Evolution/
│   ├── 07 Sources and Accuracy Standard.md
│   ├── 07 Sources and Accuracy/
│   ├── 08 Metadata and Status Standard.md
│   ├── 08 Metadata and Status/
│   │   └── vocabulary-base.yaml
│   ├── 09 Wiki Link and Navigation Standard.md
│   ├── 09 Wiki Link and Navigation/
│   ├── 10 Writing and Formatting Standard.md
│   ├── 10 Writing and Formatting/
│   ├── 11 Expression Layer Standard.md
│   ├── 11 Expression Layer/
│   ├── 12 Quality Assurance Standard.md
│   ├── 12 Quality Assurance/
│   └── Read Sets/
├── profiles/
│   ├── README.md
│   └── agent-atlas/
│       ├── profile.md
│       ├── scope-and-architecture.md
│       ├── priority-rubric.md
│       ├── language-contract.md
│       ├── expression-layer.md
│       ├── source-policy.md
│       ├── vocabulary-extensions.yaml
│       ├── card-compatibility.md
│       ├── registries/
│       │   ├── roles.md
│       │   ├── audit-dimensions.md
│       │   ├── registered-scans.md
│       │   └── routing-and-gates.md
│       └── interview/
│           ├── 11 Interview Content Standard.md
│           ├── 01 Interview Architecture and Separation.md
│           ├── 02 Card Granularity Coverage and Categories.md
│           ├── 03 Card Structure and Answer Levels.md
│           ├── 04 System Deep Dive and Bilingual Policy.md
│           ├── 05 Knowledge Links and Preparation.md
│           ├── 06 Roadmap and Question Bank.md
│           ├── 07 Migration Audit and Acceptance.md
│           └── 05 Interview Content Read Set.md
├── Tools/
│   ├── *.py
│   ├── README.md
│   ├── schemas/
│   └── vocab.yaml
├── legacy/
│   ├── cards/
│   └── migrations/
└── docs/
    ├── split_map.tsv
    ├── golden_scenarios.md
    ├── structure_proposal.md
    ├── removed_instance_log.md
    ├── blockers.md                 # 仅在出现 blocker 时创建
    └── conservation_report.md      # 阶段 4 创建
```

目录决策：

- `kernel/` 保留现有 `00–12` 的相对布局，避免把语义拆分与额外目录美化耦合。
- 原 11 域的通用部分改称 `Expression Layer`；本实例的 Interview 内容与 RS 05 进入 profile。
- `profiles/agent-atlas/interview/` 下沿用原文件名以保留映射可读性，但每个文件只承接被判为 profile 的块；同一原文件的通用 mixed 片段进入 `kernel/11 Expression Layer/`，不是整文件复制两份。
- kernel 的 Read Sets 保留 00–04、06–10；RS 05 由 profile 的 routing registry 注册。
- 当前 `Tools/` 大小写和相对布局保留。本期不改脚本内容，也不为目录风格重命名工具面。
- 11 个 Cards 原样移入 `legacy/cards/`，不重编。为避免 Card-first 行为静默变化，`card-compatibility.md` 只维护 Card ID → legacy snapshot → canonical Read Set 的解析表；它不复制 Card 正文，也不改变 source-of-truth 优先级。该兼容层只对 `agent-atlas` profile 生效，后续 profile 不自动继承。

## Profile Interface

`profiles/README.md` 只定义通用 profile 加载接口；`profiles/agent-atlas/profile.md` 绑定本实例实现。建议固定以下 slots：

| Kernel-facing slot | Agent Atlas owner | Responsibility |
|---|---|---|
| `Profile Scope` | `scope-and-architecture.md` | in-scope 主线、基础保全、排除项槽位与文件组织承诺 |
| `Priority Rubric` | `priority-rubric.md` | P0 / P1 授予条件；不替换 kernel 的三级轴和 tier 派生机制 |
| `Language Contract` | `language-contract.md` | 中文解释、英文 identity、双语标题和显示边界 |
| `Expression Layer Entry` | `expression-layer.md` | 只做 profile 路由入口；具体规则 owner 位于 `interview/` 各模块，不形成第二 owner |
| `Source Policy` | `source-policy.md` | 本实例点名的一手来源、厂商边界与扫描入口 |
| `Vocabulary Extensions` | `vocabulary-extensions.yaml` | profile-owned 的 domain / type / scope / status 扩展与实例派发表；与 kernel base vocab 合成 `Tools/vocab.yaml` |
| `Role Registry` | `registries/roles.md` | Model / Harness / Executor / Human 等扩展角色 |
| `Audit Dimension Registry` | `registries/audit-dimensions.md` | `interview` 等 profile 扩展审计维度 |
| `Registered Scan Registry` | `registries/registered-scans.md` | 中文语言与 Interview 残留等 profile 扫描 |
| `Routing And Gate Registry` | `registries/routing-and-gates.md` | profile task routes、RS 05 和扩展 gates |
| `Runtime Card Provider` | `card-compatibility.md` | 第一期间稳定 Card ID 到 legacy snapshot 与 canonical Read Set 的只读解析；后续可替换为重新编译的 active provider |

Kernel 文本只引用这些 slot 名。例如，它可以要求“由 `Priority Rubric` 给出 P0 授予条件”，但不能点名 Agent/Harness 或直接链接 `profiles/agent-atlas/`。

“本期 Cards 不重编”是当前迁移 task 的显式边界，不改写未来 governance 的行为：受影响标准再次修订时，规范仍要求同步 Runtime Card Provider 的派生产物。当前 compatibility provider 只解决本期 Card-first 回归；若未来修订发生而 active compiler 尚未建立，该 governance task 必须停在未关闭状态，不能把旧 snapshot 冒充新产物。

当前 `Tools/stamp_cards.py` 只扫描 `Cards/*.md`，无法对 `legacy/cards/` compatibility provider 完成 G07 的运行级 write-back gate。本方案推荐如实登记：本期归档施工因用户明确 no-recompile 而不运行 `stamp_cards.py --check`；G07 的规范判定仍必须回答“派生 Cards 同步与 stamp check 是关闭条件”，但在新的 active provider / tool adapter 建立前，任何后续 governance task 都不得宣称该 gate 可执行或已通过。这是确认项，不是静默放宽 golden scenario。

## Adjudication Encoding

四项用户裁决在 map 中实际影响 10 行，施工时建立显式 constants / defaults 表：

| Adjudication | Kernel invariant | Profile contribution | Override policy |
|---|---|---|---|
| ① Process / Flow roles | 最低回答谁提议、谁把关、谁执行、谁能叫停；同一主体可承担多角色 | 注册 Model / Harness / Executor / Human 角色名 | 可增加 profile 角色，不能降低四问下限 |
| ② Priority | 固定 P0 / P1 / P2 三级轴、tier 派生和配额挂钩机制 | 定义本实例 P0 / P1 授予标准 | profile 不能替换轴；可改变授予 rubric |
| ③ Audit dimensions | 固定七个基础审计维度 | 注册 `interview` 等扩展维度 | 可增加扩展维度，不能删除基础维度 |
| ④ Constants and defaults | 实质复核与 Terminal Audit 的两轮上限 | 配额、维护参数、并发和批规模可提供覆写值 | 两轮上限是不可覆写宪法常数；其余列为内核默认值 |

裁决④的可覆写默认值包括：P0 / P1 配额 `15% / 35%`、维护候选连续 `3` 轮降级、入链改指 `÷6` 折算、`concurrency_cap = 3`、S / M / L batch 上限 `24 / 10 / 6`。Profile manifest 必须列出实际覆写；未列时使用 kernel 默认值。

## Mapping Rules By Tag

Tag 与同一行 note 共同构成权威指令：tag 给出默认归宿，note 给出该行更细的切分、替换、删除或注册动作。严格执行 note 中已经明示的句级动作不构成改判；任何超出 note 的归宿变化都必须先单独修改 `split_map.tsv`，追加“施工中改判+理由”并独立提交。

| Tag | Mechanical rule | Conservation evidence |
|---|---|---|
| `kernel` | 默认整块迁入对应 `kernel/00–12` owner；按 note 完成 profile role substitution、实例片段删除或 `examples` 中性化 | 一个主要新 path + heading；note 指定的 segment action 另记；规则谓词、阈值、顺序和 gate 不变 |
| `profile` | 默认整块迁入一个 profile owner；note 明示可上浮的通用机制才进入 kernel | 一个 profile path + heading；如 note 指定上浮则同时记录其 kernel segment |
| `mixed` | 先按 note 指定的边界拆成 kernel / profile（必要时另含 instance）片段，再写两侧 | 同一 map row 记录全部 target anchors；合读语义等于原块 |
| `instance` | 从生效语料移除，写 `removed_instance_log.md` | source、heading、原因、active removal、可选 legacy target |
| `nav` | 原 nav 行只随一个主要语义继承宿主迁移；其它新文件所需导航重新生成，视为新结构元数据 | 该 404 行只有一个 conserved target；新增导航另记 provenance，不复制计数 |
| `derived` | `git mv` 到 `legacy/cards/`，不改字节、不重编 | 原文件与 legacy 文件 hash 相同 |
| `profile-derived` | kernel base 与 profile extensions 分别持有 canonical 值，生成物在原工具消费路径重新编译 | 两组输入、稳定合成步骤、build receipt、output hash |

`examples` 行只允许把 AI / Agent 味的示例替换为领域中性实体；不得借机改写规则、压缩条件、调整阈值或改变执行顺序。

## Instance And Legacy Policy

实例验收按四类分账，不能只看纯 `instance` tag：

1. 10 个纯 `instance` 行全部从生效的 kernel / profile 语料删除并逐条登记。
2. 另有 16 个 active Markdown 的 `kernel` / `mixed` / `profile` 行，其 note 明示包含部署名、版本值或其它 instance segment；这些片段也删除或归零，并以 `map row + segment` 单独登记。
3. Tools / schemas 中本期因字节守恒而保留的实例硬编码与示例进入 `conservation_report.md` 的 Tooling Deferrals，不得声称已经清除或支持 profile 注入。
4. Cards 内的实例内容随 derived snapshot 进入 legacy，只做 hash 守恒，不计入 active corpus。

16 个 active Markdown 行内 instance segments 的权威键与处置如下；这些行本身不改判，只有 note 已指定的 segment 进入删除日志：

| Source | Heading | Tag | Instance segment action |
|---|---|---|---|
| `00 Standards Overview.md` | `Purpose` | `mixed` | 删除 v1.2–v2.3 逐版本演进史 |
| `00 Standards Overview.md` | `Current State` | `mixed` | 归零 2.3、2026-07-30、13 MOC、72 modules 等部署值 |
| `00 Standards Overview.md` | `Protected Defaults` | `mixed` | 删除 `Python Algorithm Agent Training` 排除条 |
| `00 Standards Control/01 Operating Role and Reading Protocol.md` | `Default Read Sets` | `mixed` | 删除 v1.1 Archive 说明 |
| `00 Standards Control/02 Task Routing and Pre-execution.md` | `Default Constraints Snapshot` | `mixed` | 删除 `Python Algorithm Agent Training` 排除条 |
| `00 Standards Control/03 Standards Governance.md` | `Standards Control` | `mixed` | 归零 2.3 / 2026-07-30 部署值 |
| `00 Standards Control/03 Standards Governance.md` | `Leaf Module Size Budget` | `mixed` | 清空已知例外登记内容，保留登记机制 |
| `00 Standards Control/04 Control State and Scope.md` | `Scope` | `mixed` | 删除 `Python Algorithm Agent Training` 排除条 |
| `Read Sets/09 Standards Governance Read Set.md` | `Start` | `mixed` | 删除 00/07 迁移史路由行 |
| `01 Scope and Architecture/03 Foundation Preservation.md` | `Foundation Preservation Rule` | `mixed` | 删除现有部署目录指涉 |
| `02 Build Execution/03 Inventory and Coverage Reconciliation.md` | `Phase 1: Inventory` | `mixed` | 删除具体排除项，改为排除清单 role 引用 |
| `02 Build Execution/05 Batch Execution and Progress Ledger.md` | `Concurrent Batches` | `mixed` | 清空串行区已知例外登记内容 |
| `05 Terminology/04 Interview and Acceptance.md` | `Interview Relationship` | `profile` | 匿名化实例路径 |
| `10 Writing and Formatting/02 Mathematics Tables and Code.md` | `Code And Pseudocode` | `mixed` | 删除 `Python Algorithm Agent Training` 豁免句 |
| `11 Interview Content/01 Interview Architecture and Separation.md` | `Folder Structure` | `mixed` | logical directory tree 迁入 profile；仅现有部署断言与痕迹删除并登记 |
| `12 Quality Assurance/02 Rendering Verification.md` | `Rendering Verification Levels` | `kernel` | 将具名 Obsidian host 部署痕迹替换为 profile tool role 引用 |

`Tools/README.md`、脚本与 schemas 的实例片段不计入上述 16 行；它们受本期工具字节守恒约束，单列为 Tooling Deferrals。

10 个纯 `instance` 行包括：

- 迁移 / 版本史：`00 Overview / Migration Compatibility`、`00/03 Change Summary`、`00/07` 两节，以及 03、05、10、12 MOC 的 Post-migration Extensions。
- 部署 scope：`01/01 Excluded Scope` 中的具体排除项。
- 运行状态：`Tools/state/watermark.yaml`。

推荐把上述 8 个纯迁移 / 版本史行全部按原 source + heading 原样保存到 `legacy/migrations/`，采用一致原则而不是只挑两个入口文件。`00/07` 只归档两个 instance H2；该文件中仍属 kernel 的 conservation 规则不复制进 legacy。Git 历史提供文件级追溯，legacy 提供块级可读追溯；两者都不恢复这些块的 active status。

具体排除项只进入删除日志，不进入 profile；profile 只保留通用 exclusion slot。`Tools/state/watermark.yaml` 删除旧值，不在本期伪造新实例状态；通用 watermark schema 保留。

`removed_instance_log.md` 每行至少记录：map row key、segment（整行时为 `whole`）、source、heading、action、active-corpus result、legacy target（如有）和理由。所有进入 legacy 的 instance 内容仍标记为 `removed-from-active`。

## Tools And Generated Assets Boundary

本期工具边界采用兼容优先：

- `Tools/*.py` 内容保持字节不变；不修复 map note 中已识别的硬编码或配置注入问题。
- `Tools/README.md` 内容保持字节不变；其中实例化调用示例作为已知工具面遗留，不进入 kernel 规则语料。
- `Tools/schemas/*` 内容保持字节不变；模板中的实例示例值延后到独立工具阶段处理。
- `Tools/check_language.py` 虽为纯 profile 逻辑，建议物理上仍留在 `Tools/`，由 `Registered Scan Registry` 决定是否激活，避免拆散其与 `kblib.py` 的运行布局。这是“profile semantic owner 不要求 executable 位于 profile 目录”的拟议非 prose 例外，必须在确认清单中单独授权；不静默改判 TSV。
- `Tools/check_vocab.py` 中写死的配额数值、`check_freshness.py` 的 domain defaults、`check_moc.py` 的旧前缀以及其它脚本硬编码，全部登记为后续工具阶段遗留；本期不得宣称脚本已经支持 profile override。
- `Tools/stamp_cards.py` 仍只支持 `Cards/*.md`，不支持 legacy compatibility provider；本期记录为 G07 operational precondition，不改脚本、不伪造 pass。
- 保留目录大小写，避免在中文语料拆分中混入工具路径迁移。

这一定义优先满足两个显式边界：工具 / schemas 本期原样平移，且不得修改 Tools 下脚本内容。唯一例外是 map 明确标为生成物的 `vocab.yaml`，以及明确标为 instance 的 watermark state 删除。

### Vocabulary Composition

`Tools/vocab.yaml` 不是全部由 profile 拥有。它的正确合成模型是：

```text
Tools/vocab.yaml
  = kernel/08 Metadata and Status/vocabulary-base.yaml
  + profiles/agent-atlas/vocabulary-extensions.yaml
```

- Kernel base 持有跨 profile 稳定的 lifecycle、evidence maturity、level / depth、P0 / P1 / P2 axis、task state 等基础字段和值。
- Profile extensions 持有本实例的 domain / type / scope / status 扩展、派发表与其它经 map 判为 profile 的值。
- Profile 可以追加已注册扩展，不能删除、重命名或重定义 kernel base 值。
- 仓库当前没有 vocab compiler，因此本方案不把“重新编译”伪装成已有能力。阶段 3 的 Tools / generated-assets batch 使用一次性确定性生成命令：按固定 key 顺序读取两份 YAML，kernel values 在前、profile additions 按源顺序追加并去重，更新 owner paths，写回原消费位置。
- 生成命令全文、输入文件 hash、合成顺序、输出 hash 和 `check_vocab` 结果写入 build receipt，并在 `conservation_report.md` 引用；临时生成器不提交到 `Tools/`。任何不能由这两份输入重建的手工差异均视为失败。

## Link And Navigation Migration

108 个基线 Markdown 文件均包含旧 `Knowledge Base Standards/` 前缀，共 971 处；其中 11 个 Cards 占 83 处，因字节守恒将原样保留在 legacy。其余出现位置还包含 active 规则与将归档 / 删除的 instance 内容，必须先按 split map 分区，不能把 971 全部当成同一迁移范围，也不得使用全局字符串替换。

Active corpus 的链接迁移先建立：

```text
old file + old heading
  -> new semantic owner
  -> new file + new heading
  -> kernel/profile/legacy status
```

- 单归宿行更新到唯一 target。
- mixed 行按引用语义指向 kernel 或 profile anchor；需要完整行为时指向 profile manifest 的组合入口。
- heading links 在目标内容落盘后再更新；旧宿主在全部 incoming links 更新并验证前不删除。
- 每个 domain batch 只关闭它实际迁移的路径和跨域引用，不把未迁移目标伪装成已完成。
- 最终对 active corpus（`kernel/ + selected profile`）运行 missing / ambiguous / heading resolution 检查；`legacy/` 从 active link gate 排除，以逐文件 hash 和 archive manifest 验收。
- `card-compatibility.md` 中的 legacy Card target 作为显式 archive reference 单独验证存在性，不要求 legacy Card 内部的旧前缀通过 active link gate。

### Split-map Navigation Gap

除 404 行之外，源文件还有 71 个真实的顶层导航 H2 未出现在 TSV：70 个 `## Navigation` 和 1 个 `## Navigation（导航）`。另有 5 个看似 H2 的字符串位于 fenced examples 内，不是结构标题，不计入缺口。

40 个 `nav` tag 只覆盖 Related / Related Standards 等尾部导航，不能自动证明这 71 个首部导航块已有施工归宿。推荐裁决：

1. 将 71 个块定义为“非规则、隐式文件导航”，每个原块随一个主要 successor host 迁移；split 后其它 target 所需导航作为新结构元数据重建，不重复计算原块。
2. 不给 `split_map.tsv` 增加新规则行，保持权威 404 行不变。
3. 在 `conservation_report.md` 增加一个不计入 404 的 Navigation Appendix，逐个列出旧 host 与新 host。

该推荐必须在阶段 2 确认后才能执行；未确认时不得静默移动或删除这些块。

## Stage 3 Batch Order

按依赖而非编号顺序施工，每批一个逻辑域、一个英文单行 commit：

| Order | Batch | Purpose | Commit template |
|---:|---|---|---|
| 1 | Domain 01 | 建立 scope / architecture 的 kernel 与首批 profile slots | `Split domain 01 into kernel and agent-atlas profile` |
| 2 | Domain 03 | 建立 note types、ownership 与 split semantics | `Split domain 03 into kernel and agent-atlas profile` |
| 3 | Domain 04 | 迁移 depth rules 与通用 examples | `Split domain 04 into kernel and agent-atlas profile` |
| 4 | Domain 05 | 迁移 terminology 与 expression references | `Split domain 05 into kernel and agent-atlas profile` |
| 5 | Domain 06 | 迁移 intake / evolution pipeline | `Split domain 06 into kernel and agent-atlas profile` |
| 6 | Domain 07 | 迁移 source / evidence rules | `Split domain 07 into kernel and agent-atlas profile` |
| 7 | Domain 08 | 建立 metadata kernel、priority rubric 与 vocabulary owner | `Split domain 08 into kernel and agent-atlas profile` |
| 8 | Domain 09 | 迁移 link / navigation semantics | `Split domain 09 into kernel and agent-atlas profile` |
| 9 | Domain 10 | 分离通用 formatting 与中文语言合同 | `Split domain 10 into kernel and agent-atlas profile` |
| 10 | Domain 11 | 分离通用 expression layer 与 Interview profile | `Split domain 11 into kernel and agent-atlas profile` |
| 11 | Domain 12 | 分离 QA kernel、扩展维度与 profile scans | `Split domain 12 into kernel and agent-atlas profile` |
| 12 | Domain 02 | 在依赖稳定后迁移 execution、defaults 与 constants | `Split domain 02 into kernel and agent-atlas profile` |
| 13 | Read Sets | 重建 kernel routes 与 profile route registry | `Split read sets into kernel and agent-atlas routes` |
| 14 | Domain 00 | 最后重建 overview、control、routing 与 profile loader | `Split domain 00 into kernel and agent-atlas profile` |
| 15 | Derived Cards | 原样归档 11 个 Cards，并建立 agent-atlas Card compatibility resolver | `Archive v2.3 runtime cards with compatibility routing` |
| 16 | Tools / generated assets | 处理 vocab 合成、watermark 删除与工具面逻辑登记；其它工具字节不变 | `Align tools with profile-generated assets` |

若施工中确需改判某一 TSV 行，先单独修改 `split_map.tsv` 并在 note 追加“施工中改判+理由”，以独立 commit 提交；不得夹入 domain batch。

8 个 migration / version-history instance blocks 随各自来源 domain commit 写入 `legacy/migrations/`，不集中到最后一批，保证来源、删除日志和 archive target 同 commit 可审。

## Per-batch Invariants

1. 以阶段 2 commit 的父快照作为内容守恒源，不以已迁移路径反推原文。
2. 先创建 kernel / profile targets，再删除旧宿主；旧宿主有未更新 incoming link 时不得删除。
3. 每个 kernel / profile 行内容零丢失；mixed 行的全部 targets 合读等价于原块。
4. 先建立 profile slot，再把 kernel 的实例点名改成角色引用。
5. `examples` 只替换领域实体，不改变规则谓词、阈值、顺序、状态或 gate。
6. 宪法常数与可覆写默认值分别登记；profile manifest 只能覆写后者。
7. instance 即使保存在 legacy，也必须登记为从 active corpus 删除。
8. `Tools/README.md`、Tools 脚本与 schemas 做 hash 守恒；Cards 归档前后做逐文件 hash 守恒。
9. 当前 batch 的 map rows 全部写出 provisional conservation destinations；不得把遗漏留到最终报告才发现。
10. mixed 无法无损拆分时写 `docs/blockers.md` 并跳过；累计超过 10 行即暂停。
11. 每批只提交该域、必要 profile targets、该域删除日志和该域链接更新；工作树中其它路径不得混入。
12. 所有标准正文保持中文，不做翻译；既有 English identity、路径、字段和代码按原语义保留。

## Stage 4 Acceptance Plan

`docs/conservation_report.md` 最终必须证明：

- 404 / 404 map rows 均有 destination 或 instance deletion record；没有重复 key、遗漏或无依据新 owner。
- 218 kernel、92 mixed、32 profile、10 instance、40 nav、11 derived、1 profile-derived 行全部按各自规则闭环。
- 71 个隐式 Navigation blocks 在单独 appendix 中逐项有 host，不污染 404 分母。
- 11 个 legacy Cards 与原文件逐字节一致；Card compatibility resolver 对 G01–G12 返回与基线相同的 Card IDs 和 canonical Read Sets。
- G07 仍判定派生 Card 同步与 stamp check 是关闭条件；由于当前 `Tools/stamp_cards.py` 不支持 legacy provider，本期报告必须把运行级 check 标为未执行的 operational precondition，不能记作 pass。
- `Tools/README.md`、Tools scripts 与 schemas 逐字节一致；vocab output 有可复现 build receipt；watermark instance state 已删除。
- 10 个纯 instance 行与 16 个 active Markdown instance segments 全部进入删除日志；active kernel / profile 不再含旧部署状态或版本史。Tools / schemas 延期项与 legacy Cards 分别列入非 active 遗留清单。
- 两项两轮上限在 kernel 标记为不可覆写；所有默认值在 profile manifest 有明确使用默认或覆写的结果。
- Active corpus 的链接检查通过，legacy archive 通过 hash / manifest 检查；新 kernel 不点名实例内容。
- 按 `kernel + profiles/agent-atlas` 合并阅读复跑 G01–G12，12 / 12 判定与基线一致；不一致项修复后只复检一次，第二次仍不一致则暂停。
- 阶段 4 以英文单行 commit `Add conservation and golden scenario verification report` 结束；最终 Git 工作树干净，且未推送任何远程。

## Confirmation Checklist

阶段 3 开始前需要用户确认以下整组推荐：

1. 采用上述 `kernel/ + profiles/agent-atlas/ + Tools/ + legacy/ + docs/` 结构，并将 kernel 的原 11 域更名为 `Expression Layer`。
2. Cards 原样进入 `legacy/cards/`，同时由 agent-atlas 的非重编 Runtime Card compatibility provider 保留稳定 Card ID → legacy snapshot → canonical Read Set 路由；Cards 只读、非 canonical，未来 profile 不继承。本期 no-recompile 不取消未来 governance 对派生产物同步的要求。需同时接受：现有 `Tools/stamp_cards.py --check` 无法扫描 legacy provider，本期按未执行 precondition 登记；在 active provider / tool adapter 建立前，后续 governance task 不得关闭该 gate。
3. 将 TSV 未列出的 71 个真实 Navigation H2 作为隐式文件导航：每个原块只随一个主要 successor host 迁移，额外导航是新结构元数据；阶段 4 以独立 appendix 对账，不修改 404 行分母。
4. 将 `profile-derived` 解释为 `kernel base vocab + selected profile extensions -> Tools/vocab.yaml`；以两份 machine-readable inputs、固定 merge 规则和 build receipt 重编，输出仍在原工具消费位置。
5. 授权 `Tools/check_language.py` 的非 prose 物理归宿例外：semantic owner 为 agent-atlas profile，文件仍留 `Tools/` 并由 registry 激活，不改判 TSV；若不接受，必须先单独改判再另定打包方式。
6. 保留 `Tools/` 当前大小写；`Tools/README.md`、脚本与 schemas 字节不变，硬编码和模板示例进入 Tooling Deferrals；只有 vocab 生成物重编、watermark instance state 删除。
7. 删除登记同时覆盖 10 个纯 instance 行和 16 个 active Markdown 行内 instance segments；Tools / schemas 延期项、legacy Cards 与 active deletion 分账验收。
8. 将全部 8 个纯 migration / version-history instance blocks 按原块存入 `legacy/migrations/`，但 `00/07` 的 kernel conservation 内容不归档；其余 instance 内容只登记、不进入 profile。
9. 链接 gate 只覆盖 active `kernel + selected profile`；legacy 排除并用 hash / manifest 验收，Card resolver 的 archive targets 单独做存在性检查。
10. 采用 16 个阶段 3 batches、英文单行 commits、中文正文不翻译，以及阶段 4 独立英文单行 commit 的施工顺序。

收到确认或修改意见前，阶段 3 不开始。
