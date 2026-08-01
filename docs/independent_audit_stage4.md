# Cambium Stage 4 独立复核报告（Independent Audit）

**复核者**：独立于施工方的第二执行上下文
**对象**：Stage 3 完成快照 `c3a7017` ＋ Stage 4 报告 commit `79328cd`
**方法**：不采信施工方结论，全部证据独立重算——404 行 ledger×map×文件系统三方对账程序化重跑、604 个目标锚点存在性逐个验证、525 个目标块哈希独立复算、内核泄漏与死链全量重扫、金标准场景锚点抽样重放（G07/G09/G11/G12）、四项裁决逐条对照最终文本。

## 一、结论

**放行。** 守恒证明成立，行为回归通过，纪律记录完整。发现 1 项 P2 级标注缺口与 2 项清理项，均不阻断；建议随下一个 commit 一并处理。

## 二、独立验证结果

**守恒对账（独立重算，全部通过）**：404/404 map 行在 ledger 中有唯一对应（零缺失、零多余、零重复键）；ledger 与 map 的标签零漂移；604 个目标锚点（文件＋标题）全部真实存在；71 个隐式 Navigation 块宿主全部存在；31 条 RI 删除记录与 ledger 双向引用完全闭合；blockers 为 0。

**块哈希独立复算**：435/525 直接匹配。90 个失配经逐一取证全部定性为**良性时点哈希**——ledger 记录的是该行所属批次写入时刻的块内容哈希，其后合法变更来自两类：(a) 后续批次对共享 profile 块的追加写入（所有多写者块的最后写入者哈希均与现状一致）；(b) 后续批次的跨域链接前缀迁移（`Knowledge Base Standards/`→`kernel/`，经 git diff 取证仅链接改写、内容零变，样本：12/07 两处、03 MOC Applicable Read Sets——其记录哈希经"旧前缀还原"复算后精确命中）。无一例内容丢失或篡改。

**机械终扫**：active 语料旧前缀残留 0；内核泄漏终扫 0（含 Agent/Harness、面试、中文优先、Obsidian、厂商名、实例路径全词表）；active 语料内部链接 997 条、死链 0；11 张 Cards 与 Tools 全部脚本/README/schemas 对基线逐字节守恒（v2.3 快照哈希一致）；watermark 实例状态已删除；vocab 重编带 build receipt 且诚实声明生成器未持久化。

**场景回归**：施工方 12/12 首轮一致且逐场景给出规范锚点；本复核独立重放 G07/G09/G11/G12 的全部关键判定锚点，与冻结基线一致。特别核验：封闭清单七项及 integrator 串行执行点、并发准入三条件＋迁移批独占、复核两轮收敛与升级条款、治理五步＋stamp check 义务。G07 的 stamp check 运行级前置被如实登记为 UNSUPPORTED/UNRUN 而非 PASS——处置正确。

**四项裁决落地**：①四问下限＋profile 角色绑定 ✓；②三级优先级轴固定于内核、授予定义入 rubric ✓；③内核七基础维度＋`interview` 作 profile 扩展维度登记 ✓；④可调参数全部带"kernel default＋profile 可覆写"标注且 profile manifest 有机读默认值表（8 项全部 use-kernel-default）✓——但见下方 F-1。

## 三、发现（不阻断）

**F-1（P2）宪法常数缺少显式"不可覆写"标注。** 裁决④与已确认的结构方案 Adjudication Encoding 表均规定"实质复核与终审的两轮上限为不可覆写宪法常数"。现状：两轮上限规则本体完好（12/01、12/06），且正确地**不在**任何可覆写默认值表中——按"profile 只能覆写内核显式开放项"的封闭语义，隐式上已经不可覆写。但内核文本中没有任何一句显式否定标注（全库 grep"不可覆写/宪法/constants"为空）。本体系的历史教训（v2.0 删层经残留条款复活）表明：靠隐式的封闭语义防守，不如一句显式否定。**建议修复**：在 12/01 与 12/06 的两轮上限条款处各加一句"本上限为 kernel 固定常数，不属于 profile 或 task contract 可覆写的默认值"。两句话，无新机制。

**F-2（清理）**：根目录残留 8 个空目录（旧域壳＋Tools/state），`rmdir` 即可；仓库根另有复核过程产生的 `_transfer_snapshot.tgz`（本复核者为传输快照所置，未跟踪），应删除。

**F-3（备忘，非缺陷）**：ledger 的 target_block_sha256 为写入时点语义，最终快照上重验会命中上述 90 处良性失配；建议在 conservation_report 或 ledger 头注释补一句哈希语义说明，防止后来者误判。

## 四、放行边界（与施工方报告一致，本复核确认）

Runtime Cards 为只读归档＋兼容解析层，未来任何 Card governance 修订在 active provider/工具适配建立前不得关闭 write-back gate；check_vocab 记录为 NO-FAIL-WITH-CANDIDATES；真实实例部署时 watermark 状态须重新初始化。这些边界已在 profile 与报告中如实登记，不构成隐藏负债。

## 五、复核后状态

第一期（中文语料 kernel/profile 拆分）达到合格交付标准。后续阶段依序为：F-1/F-2 修复 → 英文化（独立工程，含内容守恒审计）→ 工具阶段（脚本 profile 注入、check_language 拆壳、stamp_cards 适配 provider）→ 第二 profile 验收 → prior art 深扫与发布打包。
