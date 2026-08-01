## Change Summary

| Version | Date | Change |
|---|---|---|
| `2.3` | `2026-07-30` | 收尾修订（v2.2 全量审计结果，全部为删除/收敛/回写）：00/02 批次清单步 9–11 改为两阶段引用（与 02/05 一致）并重编受影响 Cards；删除 12/07 与 12/04 的"高风险"常驻审残留（v2.0 删层后门）；枢纽页同步指定 integrator 合并后独立小步；12/07 needs_rereview 改走 delta 通道；check_vocab 正式纳入封闭清单第 7 项（原本已批关闭全库运行，仅归位，无新层）；迁移批独占执行显式化；12/06 终审与 02/06 恢复并发化措辞；跨批缺链记 delta 由维护轮消化；串行区三处已知例外如实登记；delta 增 `watermark_advance` 字段；7 处 Module Index 登记回写；Registry 修正 3 行（删幽灵闸"状态/Ledger 一致性"行）；Tools 层版本戳统一；stamp_cards 覆盖 card-index 且修订关闭前须 `--check` 通过（对应既有 Write-back 义务的机器兜底）；新增 `Tools/check_moc.py`（12/05 既有人工检查项的脚本化，候选级）。changed-predicate 清单：封闭清单第 7 项、批次关闭执行点表述（00/02 步 9–11）、迁移批准入。存量凭证零失效（check_vocab 原已全库运行） |
| `2.2` | `2026-07-30` | 串行区提纯与批次规模分级：12/03 关批清单分为批内项（merge-ready 前提，可并行）与全局项（串行合并核验），串行区仅确定性动作；批次规模按档位分级（S ≤24、M ≤10、L ≤6）；新增 Tools/apply_delta.py（delta 确定性应用，替代 LLM 手编 Ledger）与 Tools/stamp_cards.py（卡片盖戳）；执行端自建持久工具须经轻量 governance 登记纳入 Tools/。changed-predicate 清单：Batch Review 分组执行点、批次规模上限。存量凭证零失效 |
| `2.1` | `2026-07-30` | 受控并发：02/05 新增 Concurrent Batches（并发准入三条件、写入权分区、merge-ready 与串行合并，`concurrency_cap` 默认 3）；12/01 复核触发提前至成稿时并给出独立性正面定义（干净上下文 subagent 即满足，主线不得代产 receipt）；12/07 封闭清单移至串行合并执行；12/03 跨批链接规则；00/05 Control Registry 增并发写冲突行；新增 coverage_delta schema。changed-predicate 清单：批次激活条件（新增清单相交性检查）、批次状态机（增 merge-ready）、批次关闭执行点（integrator 串行合并时）、复核触发时机与 receipt 上下文标识。存量凭证零失效 |
| `2.0` | `2026-07-30` | 控制面收敛：一险一闸注册表（00/05 Control Registry）、三闸门词可计算定义（Batch-close Closed List、changed-predicate 受影响范围、fingerprint 显式字段清单）、生产限流、终审单调化（Terminal Findings And Convergence）、18 项删层。changed-predicate 清单（本修订自举使用新机制）：1) 批级人工审范围改为 changed ∪ invalidated ∪ 抽样；2) AuditPlan 每批仅关闭前一次；3) Guidance 门槛改“重要”正面定义；4) `artifact_fingerprint` 排除状态轴字段（旧凭证只会更易复用，不作废）；5) 批次关闭封闭清单六项固定；6) 终审 findings 分级与两轮上限；7) 维护轮候选池扩为四源＋过期降级；8) Cards hash 失配不再阻断执行 |
| `1.9` | `2026-07-23` | 阅读协议现代化：00/01 Mandatory Reading Protocol 与 Overview Start Here 重写为 Card-first 默认＋Read Set 升级回读路径；`loaded module set` 演化为 `loaded set`（Cards＋升级回读 modules），同步 12 处记录义务措辞；00/01 Default Read Sets 补 Maintenance Run；Cards 01/07 同步重新生成；同版编译产物版本戳统一（cards compiled_from、vocab.yaml、Tools/README、schema 示例值） |
| `1.8.2` | `2026-07-23` | 治理补丁：12/01 实质正确性复核新增审查对象界定与收敛规则——复核判定文档级正确性而非设计无懈可击；findings 三级分级仅 critical/major 阻断；轮次上限 2 且确认轮锁定范围；超轮升级用户。修复对抗复核无终止条件导致的循环。同版过期内容清理（2026-07-23）：Overview 版本快照回写、移除与 Card-first 冲突的 v1.2 时代阅读指令、移除已失效的 195/195 守恒统计行与 Card Index 的 PENDING 占位说明 |
| `1.8.1` | `2026-07-22` | 治理补丁：00/02 Effort Tiering 新增 Priority Quota（P0 ≤15%、P1 ≤35%，超配须降级或记录豁免，对账检查分布）；12/01 实质正确性复核新增存量豁免（触发时机以三种情形为限，标准版本升级不重开存量已 reviewed 且未过期页面的人工复核）；check_vocab.py 增加 priority/tier 分布统计与超配候选输出 |
| `1.8` | `2026-07-21` | 瘦身：v1.1 Legacy 归档至 vault Archive/、13 个 MOC 的 Original Section Map 移除、leaf Navigation 的 Canonical sections 行移除、00/07 压缩、10/05 与 12/07 减脂；引擎：保质期与 volatility（08/05、08/01）、外部水位线（06/03）、Maintenance Run 与预算封套（00/02、00/06、RS 10、Card 10）、内容级失效传播（12/07）、实质正确性复核（12/01）、退役与合并工作流（03/03）、lifecycle 字段；新增 check_freshness.py 与 watermark schema |
| `1.7` | `2026-07-21` | 新增编译产物层（Cards/ 九张 Runtime Card＋Card Index）与确定性检查工具层（Tools/ 四脚本＋schemas＋vocab.yaml）；00/01 新增 Card-first Reading Mode；00/02 新增 Effort Tiering（S/M/L）；12/03 gate 合并规则；Ledger 与 receipt 机读化（02/03、02/05、12/07）；08/01 补 `runtime-card` 类型 |
| `1.6` | `2026-07-21` | 一致性修复：跨域重复收敛（Terminal Proof/Audit、状态词表、模板、来源政策、语言政策引用化）、Cross-domain Rule Registry 与 Revision Write-back Checklist 建立、Read Set 路由补全（Pre-execution Gate 入 bootstrap、Status Axes 入单页写作、Migration Map 入治理）、`Tools/duplicate_check.py` 重复检测 |
| `1.5` | `2026-07-18` | 新增独立 Chinese-first Technical Language 规则：文件名保持纯英文；英文标题和首次术语统一使用 `English（中文）`；定义表格、图表、Source、Interview 例外、自动候选检查和按维度失效边界，并接入 authoring、module、source、interview 与 audit Read Sets |
| `1.4` | `2026-07-18` | 将重复审计改为分层证据复用：新增dimension-specific AuditReceipt、artifact/dependency/contract fingerprint、失效传播、专项Audit边界与Terminal增量人工复核；保留最终快照的全量便宜确定性检查 |
| `1.3` | `2026-07-18` | 将渲染验收改为 deterministic-first、visual-by-exception；新增 targeted visual、expanded UI 与 temporal recording 的客观升级条件，并明确无 trigger 时不要求 UI 证据 |
| `1.2` | `2026-07-17` | 将 `00–12` 全部 Standards 无删减拆分为 folder-based modules；增加 domain MOC、module-level Read Sets、旧章节迁移映射、兼容入口和 loaded module tracking |
| `1.1` | `2026-07-17` | 增加 Mid-task Guidance、Amendment Record、safe switching、contract / scope / queue / batch versioning、用户 hypothesis 与 source lead 证据边界，以及 Guidance Reconciliation Gate |
| `1.0` | `2026-07-17` | 分离 task、authoring、interview、evidence 与 learning 状态；增加时间语义、Coverage Ledger、Required Queue、Process / Flow、风险渲染、Migration Audit、Terminal Audit 和 Terminal Proof |
## Conservation Metadata

- Status: `removed-from-active`
- Source: `00 Standards Control/03 Standards Governance.md#Change Summary`
- Evidence: `docs/removed_instance_log.md`
